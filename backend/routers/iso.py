import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional

from iso_tasks import generate_client_iso_task, download_base_iso_task, CACHE_DIR
from models import TaskLog
from database import SessionLocal

router = APIRouter()

class GenerateIsoRequest(BaseModel):
    target_ip: str
    auth_token: str

class BaseIsoDownloadRequest(BaseModel):
    url: Optional[str] = None

@router.post("/generate")
def generate_iso(req: GenerateIsoRequest):
    try:
        task = generate_client_iso_task.delay(req.target_ip, req.auth_token)
        return {"task_id": task.id, "message": "ISO generation task started."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download_base")
def trigger_base_download(req: BaseIsoDownloadRequest = None):
    # Prevent concurrent duplicate download tasks if one is already running
    base_iso_path = os.path.join(CACHE_DIR, "base.iso")
    base_exists = os.path.exists(base_iso_path) and os.path.getsize(base_iso_path) > 1000 * 1024 * 1024
    lock_path = os.path.join(CACHE_DIR, "download.lock")
    
    if not base_exists and os.path.exists(lock_path):
        raise HTTPException(status_code=400, detail="Base ISO download is already in progress.")

    if not base_exists:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(lock_path, "w") as f:
            f.write("LOCKED")

    try:
        url = req.url if req else None
        task = download_base_iso_task.delay(url=url)
        return {"task_id": task.id, "message": "Base ISO download started."}
    except Exception as e:
        if not base_exists and os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload_base")
def upload_base_iso(file: UploadFile = File(...)):
    if not file.filename.endswith(".iso"):
        raise HTTPException(status_code=400, detail="Only .iso files are allowed")
    
    os.makedirs(CACHE_DIR, exist_ok=True)
    base_iso_path = os.path.join(CACHE_DIR, "base.iso")
    
    try:
        with open(base_iso_path, "wb") as f:
            import shutil
            shutil.copyfileobj(file.file, f)
        
        # Save actual size for progress UI
        with open(os.path.join(CACHE_DIR, "base.iso.size"), "w") as f:
            f.write(str(os.path.getsize(base_iso_path)))
            
        return {"status": "SUCCESS", "message": "Base ISO uploaded successfully."}
    except Exception as e:
        if os.path.exists(base_iso_path):
            os.remove(base_iso_path)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@router.delete("/base")
def clear_base_iso():
    base_iso_path = os.path.join(CACHE_DIR, "base.iso")
    size_file = os.path.join(CACHE_DIR, "base.iso.size")
    client_iso_path = os.path.join(CACHE_DIR, "technician_client_v1.iso")
    if os.path.exists(base_iso_path):
        os.remove(base_iso_path)
    if os.path.exists(size_file):
        os.remove(size_file)
    if os.path.exists(client_iso_path):
        os.remove(client_iso_path)
    return {"status": "SUCCESS", "message": "Base ISO cache cleared."}

@router.get("/download")
def download_iso():
    iso_path = os.path.join(CACHE_DIR, "technician_client_v1.iso")
    if not os.path.exists(iso_path):
        raise HTTPException(status_code=404, detail="Client ISO not found. Generate it first.")
    
    return FileResponse(
        path=iso_path,
        filename="Borg_Restore_Technician_Client.iso",
        media_type="application/x-iso9660-image"
    )

@router.get("/status")
def get_iso_status():
    base_iso_path = os.path.join(CACHE_DIR, "base.iso")
    base_exists = os.path.exists(base_iso_path) and os.path.getsize(base_iso_path) > 1000 * 1024 * 1024
    tmp_path = os.path.join(CACHE_DIR, "base.iso.tmp")
    lock_path = os.path.join(CACHE_DIR, "download.lock")
    client_exists = os.path.exists(os.path.join(CACHE_DIR, "technician_client_v1.iso"))
    
    progress = -1
    if not base_exists and os.path.exists(lock_path):
        progress = 0
        if os.path.exists(tmp_path):
            size = os.path.getsize(tmp_path)
            total_size = 4139925504
            size_file = os.path.join(CACHE_DIR, "base.iso.size")
            if os.path.exists(size_file):
                try:
                    with open(size_file, "r") as f:
                        total_size = int(f.read().strip())
                except:
                    pass
            progress = min(100, int((size / total_size) * 100))
        
    return {
        "base_iso_cached": base_exists or client_exists,
        "base_iso_progress": progress,
        "client_iso_ready": client_exists
    }

import subprocess
from fastapi.responses import StreamingResponse

@router.get("/repos/{hostname}/download")
def download_repo(hostname: str, token: str):
    token_path = os.path.join(CACHE_DIR, "auth_token.txt")
    expected_token = "offline-token-1234"
    if os.path.exists(token_path):
        try:
            with open(token_path, "r") as f:
                expected_token = f.read().strip()
        except:
            pass
    
    if token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    repo_dir = f"/data/borg/fleet/{hostname}"
    if not os.path.exists(repo_dir):
        raise HTTPException(status_code=404, detail="Repository not found")
        
    # Get total size of repository directory to send in X-Total-Size header
    total_size = 0
    try:
        du_out = subprocess.check_output(["du", "-sb", repo_dir]).decode().strip()
        total_size = int(du_out.split()[0])
    except Exception as e:
        for root, dirs, files in os.walk(repo_dir):
            for file in files:
                total_size += os.path.getsize(os.path.join(root, file))
                
    def tar_generator():
        proc = subprocess.Popen(
            ["tar", "-cf", "-", "-C", "/data/borg/fleet", hostname],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.terminate()
            proc.wait()
            
    return StreamingResponse(
        tar_generator(),
        media_type="application/x-tar",
        headers={
            "Content-Disposition": f"attachment; filename={hostname}.tar",
            "X-Total-Size": str(total_size)
        }
    )

