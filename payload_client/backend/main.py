import os
import subprocess
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# We will inject the shared disk_ops.py into core/disk_ops.py during ISO generation
try:
    from core.disk_ops import format_and_restore
except ImportError:
    pass # Will be resolved at ISO runtime

# Centralized version logic
try:
    from version import VERSION
except ImportError:
    VERSION = "v0.5beta"

app = FastAPI(title="Offline Technician Client", version=VERSION)

# Try to register the shared network configurations router if available
try:
    from routers.network import router as network_router
    app.include_router(network_router, prefix="/api")
except ImportError:
    pass

# Local state to track task progress
task_logs: Dict[str, str] = {}
task_status: Dict[str, str] = {}
task_progress: Dict[str, int] = {}

class RestoreRequest(BaseModel):
    node_id: int
    archive_name: str
    target_dev: str
    override_mismatch: bool = False
    keep_network_configs: bool = True
    wipe_mac_bindings: bool = False

def run_offline_restore(task_id: str, req: RestoreRequest):
    task_status[task_id] = "RUNNING"
    task_progress[task_id] = 0
    task_logs[task_id] = f"Starting offline restore for archive {req.archive_name} to {req.target_dev}\n"

    def log_callback(msg: str, prog: Optional[int] = None, status: Optional[str] = None):
        if prog is not None:
            task_progress[task_id] = prog
            task_logs[task_id] += f"[PROGRESS] {prog}:{msg}\n"
        else:
            task_logs[task_id] += f"{msg}\n"
        if status:
            task_status[task_id] = status

    # In a real offline scenario, we don't have the node DB, so we use a default layout
    partitions = [
        {"name": "ESP", "mount": "/boot/efi", "fstype": "vfat", "label": "EFI", "uuid": "458C-37BB", "size_bytes": 512 * 1024 * 1024},
        {"name": "boot", "mount": "/boot", "fstype": "ext2", "label": "edgeboot", "uuid": "", "size_bytes": 1024 * 1024 * 1024},
        {"name": "root", "mount": "/", "fstype": "ext4", "label": "edgeroot", "uuid": "", "size_bytes": 30 * 1024 * 1024 * 1024},
        {"name": "log", "mount": "/var/log/edge", "fstype": "ext4", "label": "edgelog", "uuid": "", "size_bytes": 5 * 1024 * 1024 * 1024},
        {"name": "storage", "mount": "/var/opt/edge", "fstype": "ext4", "label": "edgestor", "uuid": "", "size_bytes": 0}
    ]

    try:
        # Assuming the persistent USB partition is mounted at /media/usb-data
        # We will create a sync endpoint to download repos there.
        repo_path = "/media/usb-data/borg/fleet"
        
        # We can't query total files easily without DB, pass 0 to disable accurate estimation
        format_and_restore(
            target_dev=req.target_dev,
            partitions=partitions,
            efi_uuid="458C-37BB",
            archive_name=req.archive_name,
            repo_path=repo_path,
            keep_network_configs=req.keep_network_configs,
            wipe_mac_bindings=req.wipe_mac_bindings,
            network_iface="eth0",
            total_files=0,
            log_callback=log_callback
        )
    except Exception as e:
        log_callback(f"FATAL EXCEPTION: {str(e)}", status="FAILED")

@app.get("/api/version")
def get_version():
    """Returns the unified application version."""
    return {"version": VERSION}

@app.get("/api/scanner/devices")
def scan_devices():
    try:
        out = subprocess.check_output("lsblk -J -b -o NAME,SIZE,MODEL,ROTA,TRAN", shell=True, text=True)
        data = json.loads(out)
        devices = []
        for bd in data.get("blockdevices", []):
            if not bd.get("name").startswith("loop") and not bd.get("name").startswith("sr"):
                is_usb = bd.get("tran") == "usb"
                # Exclude the USB drive we booted from if possible.
                try:
                    mounts = subprocess.check_output(f"lsblk -J -o MOUNTPOINT /dev/{bd['name']}", shell=True, text=True)
                    if "live" in mounts.lower():
                        continue
                except:
                    pass
                
                devices.append({
                    "name": f"/dev/{bd['name']}",
                    "size": bd.get("size", 0),
                    "model": bd.get("model", "Unknown Model"),
                    "rotational": bd.get("rota", False),
                    "disk_type": "NVME" if "nvme" in bd["name"] else "SATA",
                    "is_usb": is_usb
                })
        return devices
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/nodes")
def get_mock_node():
    return [{
        "id": 1,
        "hostname": "Offline Mode (Local Cache)",
        "ip_address": "127.0.0.1",
        "disk_type": "UNKNOWN",
        "efi_uuid": "458C-37BB",
        "last_backup": "Available"
    }]

@app.get("/api/stats")
def get_mock_stats():
    repo_path = "/media/usb-data/borg/fleet"
    total_original = 0
    total_dedup = 0
    
    if os.path.exists(repo_path):
        env = os.environ.copy()
        env["BORG_PASSPHRASE"] = os.getenv("BORG_PASSPHRASE", "")
        try:
            out = subprocess.check_output(["borg", "info", "--json", repo_path], env=env, text=True)
            data = json.loads(out)
            cache_stats = data.get("cache", {}).get("stats", {})
            total_original = cache_stats.get("total_size", 0)
            total_dedup = cache_stats.get("total_csize", 0)
        except Exception:
            pass

    ratio = 1.0
    if total_dedup > 0:
        ratio = round(total_original / total_dedup, 2)

    return {
        "total_nodes": 1,
        "total_original_size_bytes": total_original,
        "total_deduplicated_size_bytes": total_dedup,
        "deduplication_ratio": ratio
    }

@app.get("/api/nodes/history")
def get_all_history():
    return get_local_history(node_id=1)

@app.get("/api/nodes/{node_id}/history")
def get_local_history(node_id: int):
    # Scan the local /media/usb-data/borg/fleet repo using borg list
    repo_path = "/media/usb-data/borg/fleet"
    if not os.path.exists(repo_path):
        return []
    
    env = os.environ.copy()
    env["BORG_PASSPHRASE"] = os.getenv("BORG_PASSPHRASE", "")
    try:
        out = subprocess.check_output(["borg", "list", "--json", repo_path], env=env, text=True)
        data = json.loads(out)
        archives = data.get("archives", [])
        snapshots = []
        for i, a in enumerate(archives):
            snapshots.append({
                "id": i,
                "node_id": node_id,
                "archive_name": a["name"],
                "timestamp": a["start"],
                "original_size": a.get("stats", {}).get("original_size", 0),
                "deduplicated_size": a.get("stats", {}).get("deduplicated_size", 0),
                "comment": a.get("comment", ""),
                "status": "SUCCESS"
            })
        return snapshots
    except Exception as e:
        return []

@app.post("/api/restore")
def trigger_restore(req: RestoreRequest, background_tasks: BackgroundTasks):
    import uuid
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    background_tasks.add_task(run_offline_restore, task_id, req)
    return {"task_id": task_id}

@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "status": task_status[task_id],
        "progress": task_progress.get(task_id, 0),
        "logs": task_logs.get(task_id, "")
    }

# Fallback to serve the React frontend built for the offline client
if os.path.exists("frontend_build"):
    app.mount("/", StaticFiles(directory="frontend_build", html=True), name="frontend")
