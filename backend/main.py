import os
import subprocess
import uuid
from typing import List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from tasks import run_bootstrap_task, run_prepare_task, run_backup_task, flash_restore_device

app = FastAPI(title="Borg Backup & Bare-Metal Restore Orchestrator API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db_init():
    """
    Ensure settings are initialized in the database on startup.
    """
    db = next(get_db())
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
    db.close()


@app.get("/api/settings", response_model=schemas.SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    """
    Retrieves global orchestrator settings.
    """
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
    return settings


@app.post("/api/settings", response_model=schemas.SettingsResponse)
def update_settings(payload: schemas.SettingsBase, db: Session = Depends(get_db)):
    """
    Updates global orchestrator settings.
    """
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)

    settings.borg_ssh_port = payload.borg_ssh_port
    settings.borg_repo_path = payload.borg_repo_path
    settings.keep_daily = payload.keep_daily
    settings.keep_weekly = payload.keep_weekly
    settings.keep_monthly = payload.keep_monthly
    settings.global_exclusions = payload.global_exclusions
    db.commit()
    return settings


@app.get("/api/nodes", response_model=List[schemas.NodeResponse])
def get_nodes(db: Session = Depends(get_db)):
    """
    Retrieves lists of all nodes.
    """
    return db.query(models.Node).all()


@app.post("/api/nodes", status_code=status.HTTP_201_CREATED)
def add_node(payload: schemas.NodeCreate, db: Session = Depends(get_db)):
    """
    Registers a new node and triggers its background bootstrap process.
    """
    # Check duplicate
    existing = db.query(models.Node).filter(
        (models.Node.hostname == payload.hostname) | 
        (models.Node.ip_address == payload.ip_address)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Node with this hostname or IP address already exists."
        )

    node = models.Node(
        hostname=payload.hostname,
        ip_address=payload.ip_address,
        ssh_port=payload.ssh_port,
        status="NEEDS_BOOTSTRAP"
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    # Spawn bootstrap Celery task
    task = run_bootstrap_task.delay(node.id, payload.bootstrap_password, payload.bootstrap_user)
    return {"message": "Node registered successfully. Bootstrap triggered.", "task_id": task.id, "node_id": node.id}


@app.post("/api/nodes/{node_id}/prepare")
def trigger_prepare(node_id: int, db: Session = Depends(get_db)):
    """
    Triggers the Auto-Prepare disk labels playbook task for a node.
    """
    node = db.query(models.Node).filter(models.Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    node.status = "NEEDS_FIX"
    db.commit()

    task = run_prepare_task.delay(node.id)
    return {"message": "Auto-prepare playbook execution triggered.", "task_id": task.id}


@app.post("/api/nodes/{node_id}/backup")
def trigger_backup(node_id: int, db: Session = Depends(get_db)):
    """
    Triggers immediate remote backup execution.
    """
    node = db.query(models.Node).filter(models.Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    task = run_backup_task.delay(node.id)
    return {"message": "Backup execution task triggered.", "task_id": task.id}


@app.get("/api/nodes/{node_id}/history", response_model=List[schemas.BackupHistoryResponse])
def get_node_history(node_id: int, db: Session = Depends(get_db)):
    """
    Retrieves the backup snapshot history records for a specific node.
    """
    return db.query(models.BackupHistory).filter(models.BackupHistory.node_id == node_id).all()


@app.get("/api/tasks/{task_id}", response_model=schemas.TaskLogResponse)
def get_task_logs(task_id: str, db: Session = Depends(get_db)):
    """
    Fetches execution logs and status of a background task.
    """
    task = db.query(models.TaskLog).filter(models.TaskLog.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


@app.get("/api/scanner/devices", response_model=List[schemas.DeviceResponse])
def scan_devices():
    """
    Scans the orchestrator host for physical block devices (SATA/NVMe).
    Filters out the orchestrator's own root system drive.
    """
    devices = []
    try:
        # Detect orchestrator host's root drive parent
        findmnt_out = subprocess.check_output("findmnt -n -o SOURCE /", shell=True, text=True).strip()
        # e.g., /dev/sda3 -> sda, /dev/nvme0n1p2 -> nvme0n1
        host_root_disk = os.path.basename(findmnt_out)
        if "nvme" in host_root_disk:
            host_root_disk = host_root_disk.split("p")[0]
        else:
            host_root_disk = "".join([c for c in host_root_disk if not c.isdigit()])

        # Run lsblk to list devices
        lsblk_cmd = "lsblk -dno NAME,SIZE,MODEL,RO || lsblk -dno NAME,SIZE,MODEL"
        lsblk_out = subprocess.check_output(lsblk_cmd, shell=True, text=True).strip()

        for line in lsblk_out.splitlines():
            parts = line.split(None, 2)
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            size_str = parts[1].strip()
            model = parts[2].strip() if len(parts) > 2 else "Generic Disk"

            # Skip loop and host root drives
            if name.startswith("loop") or name.startswith("ram") or name == host_root_disk:
                continue

            # Check rotational flag
            rotational_path = f"/sys/block/{name}/queue/rotational"
            rotational = True
            if os.path.exists(rotational_path):
                with open(rotational_path, "r") as f:
                    rotational = f.read().strip() == "1"

            # Disk Type classification
            disk_type = "NVME" if "nvme" in name else "SATA"

            # Convert human size string to bytes estimation
            size_bytes = 0
            try:
                numeric_part = float("".join([c for c in size_str if c.isdigit() or c == "."]))
                if "G" in size_str:
                    size_bytes = int(numeric_part * 1024 * 1024 * 1024)
                elif "T" in size_str:
                    size_bytes = int(numeric_part * 1024 * 1024 * 1024 * 1024)
                elif "M" in size_str:
                    size_bytes = int(numeric_part * 1024 * 1024)
                else:
                    size_bytes = int(numeric_part)
            except Exception:
                pass

            devices.append(schemas.DeviceResponse(
                name=f"/dev/{name}",
                size=size_bytes,
                model=model,
                rotational=rotational,
                disk_type=disk_type
            ))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan local devices: {str(e)}"
        )
    return devices


@app.post("/api/restore")
def trigger_restore(payload: schemas.RestoreRequest, db: Session = Depends(get_db)):
    """
    Triggers bare-metal flashing restore process.
    Validates NVMe/SATA mismatch and starts flashing task.
    """
    node = db.query(models.Node).filter(models.Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found.")

    if not node.efi_uuid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot restore. The node's EFI ESP partition UUID was not collected. Run 'Auto-Prepare' on the node first."
        )

    # Hardware Mismatch Check
    target_disk_type = "NVME" if "nvme" in payload.target_dev else "SATA"
    if node.disk_type != "UNKNOWN" and node.disk_type != target_disk_type:
        if not payload.override_mismatch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"DISK TYPE MISMATCH WARNING: The backup node used {node.disk_type} but the target is {target_disk_type}. Confirmation required to proceed."
            )

    task = flash_restore_device.delay(node.id, payload.archive_name, payload.target_dev)
    return {"message": "Restore flashing process started.", "task_id": task.id}


@app.get("/api/stats")
def get_global_stats(db: Session = Depends(get_db)):
    """
    Retrieves global metrics including storage dedup ratios.
    """
    histories = db.query(models.BackupHistory).filter(models.BackupHistory.status == "SUCCESS").all()
    total_original = sum(h.original_size for h in histories)
    total_deduplicated = sum(h.deduplicated_size for h in histories)
    
    ratio = 1.0
    if total_deduplicated > 0:
        ratio = round(total_original / total_deduplicated, 2)

    return {
        "total_nodes": db.query(models.Node).count(),
        "total_original_size_bytes": total_original,
        "total_deduplicated_size_bytes": total_deduplicated,
        "deduplication_ratio": ratio
    }
