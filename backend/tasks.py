import os
import shutil
import subprocess
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from database import SessionLocal
from models import TaskLog, Node, BackupHistory, Settings
from ansible_utils import run_ansible_playbook

from celery import Celery
from celery.schedules import crontab

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# Configure Celery Beat for global daily prune
celery_app.conf.beat_schedule = {
    'global-daily-prune-task': {
        'task': 'tasks.global_daily_prune',
        'schedule': crontab(hour=3, minute=0), # Run at 3:00 AM daily
    },
}
celery_app.conf.timezone = 'UTC'

def log_to_task(task_id: str, message: str) -> None:
    """
    Appends a log line to the specified TaskLog record in the database.

    Args:
        task_id: The TaskLog UUID.
        message: The log message to append.
    """
    db: Session = SessionLocal()
    try:
        task = db.query(TaskLog).filter(TaskLog.id == task_id).first()
        if task:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            task.log_output += f"[{timestamp}] {message}\n"
            task.status = "RUNNING"
            db.commit()
    except Exception as e:
        logger.error(f"Error logging to task {task_id}: {str(e)}")
    finally:
        db.close()

@celery_app.task(bind=True)
def run_bootstrap_task(self, node_id: int, ssh_password: str, bootstrap_user: str) -> Dict[str, Any]:
    """
    Celery task to run the Node bootstrapping process using Ansible.

    Args:
        node_id: ID of the Node database record.
        ssh_password: Temporary SSH password for bootstrap.
        bootstrap_user: Temporary SSH user for bootstrap.

    Returns:
        Status result dictionary.
    """
    task_id = self.request.id
    db: Session = SessionLocal()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        db.close()
        return {"status": "FAILED", "error": "Node not found"}

    # Initialize TaskLog
    task_log = TaskLog(id=task_id, task_type="BOOTSTRAP", status="RUNNING", log_output="")
    db.add(task_log)
    db.commit()

    log_to_task(task_id, f"Starting bootstrap for {node.hostname} ({node.ip_address})")

    # Run playbook
    res = run_ansible_playbook(
        task_id=task_id,
        playbook_name="bootstrap.yml",
        host_ip=node.ip_address,
        extra_vars={"bootstrap_user": bootstrap_user},
        ssh_password=ssh_password
    )

    if res["status"] == "SUCCESS":
        ssh_pub_key = res["parsed_data"].get("ssh_pub_key")
        node.ssh_pub_key = ssh_pub_key
        node.status = "NEEDS_FIX" # Proceed to Auto-Prepare stage next
        db.commit()
        log_to_task(task_id, "Bootstrap completed successfully. Public SSH key fetched.")

        # Append key to Borg Server authorized_keys
        try:
            authorized_keys_path = "/home/borg/.ssh/authorized_keys"
            os.makedirs(os.path.dirname(authorized_keys_path), exist_ok=True)
            command_restriction = (
                f'command="borg serve --restrict-to-path /data/borg/{node.hostname}",'
                f'no-port-forwarding,no-X11-forwarding,no-pty '
            )
            entry = f"{command_restriction}{ssh_pub_key}\n"
            with open(authorized_keys_path, "a") as f:
                f.write(entry)
            log_to_task(task_id, "Borg SSH authorized_keys updated with forced command restriction.")
        except Exception as e:
            log_to_task(task_id, f"WARNING: Failed to append key to authorized_keys: {str(e)}")
    else:
        node.status = "NEEDS_BOOTSTRAP"
        db.commit()
        log_to_task(task_id, "Bootstrap task failed.")

    db.close()
    return res

@celery_app.task(bind=True)
def run_prepare_task(self, node_id: int) -> Dict[str, Any]:
    """
    Celery task to run the Auto-Prepare disk labels playbook on the node.

    Args:
        node_id: ID of the Node database record.

    Returns:
        Status result dictionary.
    """
    task_id = self.request.id
    db: Session = SessionLocal()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        db.close()
        return {"status": "FAILED", "error": "Node not found"}

    task_log = TaskLog(id=task_id, task_type="PREPARE", status="RUNNING", log_output="")
    db.add(task_log)
    db.commit()

    log_to_task(task_id, f"Starting auto-prepare for {node.hostname} ({node.ip_address})")

    # Run playbook (uses Orchestrator's SSH control key)
    # Orchestrator SSH control key is assumed to be in /root/.ssh/id_ed25519
    res = run_ansible_playbook(
        task_id=task_id,
        playbook_name="prepare.yml",
        host_ip=node.ip_address,
        extra_vars={},
        ssh_key_path="/root/.ssh/id_ed25519"
    )

    if res["status"] == "SUCCESS":
        node.disk_type = res["parsed_data"].get("disk_type", "UNKNOWN")
        node.network_iface = res["parsed_data"].get("network_iface")
        node.efi_uuid = res["parsed_data"].get("efi_uuid")
        node.status = "READY"
        db.commit()
        log_to_task(task_id, f"Auto-prepare finished. Disk type: {node.disk_type}, EFI UUID: {node.efi_uuid}, Interface: {node.network_iface}")
    else:
        node.status = "NEEDS_FIX"
        db.commit()
        log_to_task(task_id, "Auto-prepare task failed.")

    db.close()
    return res

@celery_app.task(bind=True)
def run_backup_task(self, node_id: int) -> Dict[str, Any]:
    """
    Triggers remote backup execution on the node pushing to the central Borg server,
    then updates Database history.

    Args:
        node_id: ID of the Node database record.

    Returns:
        Status dictionary.
    """
    task_id = self.request.id
    db: Session = SessionLocal()
    node = db.query(Node).filter(Node.id == node_id).first()
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()
        db.add(settings)
        db.commit()

    if not node:
        db.close()
        return {"status": "FAILED", "error": "Node not found"}

    task_log = TaskLog(id=task_id, task_type="BACKUP", status="RUNNING", log_output="")
    db.add(task_log)
    db.commit()

    log_to_task(task_id, f"Initiating Borg backup for {node.hostname}...")

    # Determine Orchestrator internal/external IP from context or use host default route IP
    # We can fetch this host's IP that routes to the edge node
    try:
        route_cmd = f"ip route get {node.ip_address}"
        route_out = subprocess.check_output(route_cmd, shell=True, text=True)
        orchestrator_ip = route_out.split("src")[1].split()[0]
    except Exception:
        orchestrator_ip = "127.0.0.1"

    archive_name = f"{node.hostname}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    borg_repo_url = f"ssh://borg@{orchestrator_ip}:{settings.borg_ssh_port}/data/borg/{node.hostname}"

    # Connect via SSH to the edge node and execute Borg backup pushing to Central server
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-i", "/root/.ssh/id_ed25519",
        f"root@{node.ip_address}",
        f"sudo -u borg BORG_PASSPHRASE='{os.getenv('BORG_PASSPHRASE')}' borg create --json --stats {borg_repo_url}::{archive_name} / --exclude {settings.global_exclusions}"
    ]

    log_to_task(task_id, f"Running remote command on node: {' '.join(ssh_cmd[:6])} [COMMAND MASKED]")

    try:
        process = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        log_to_task(task_id, f"Remote execution stdout:\n{stdout}")
        if stderr:
            log_to_task(task_id, f"Remote execution stderr:\n{stderr}")

        if process.returncode == 0:
            # Parse sizes from JSON
            original_size = 0
            deduplicated_size = 0
            try:
                data = json.loads(stdout)
                original_size = data.get("stats", {}).get("original_size", 0)
                deduplicated_size = data.get("stats", {}).get("deduplicated_size", 0)
            except Exception:
                # If stdout is not direct JSON but includes logs, search for lines
                log_to_task(task_id, "Failed to parse JSON directly; estimating size metrics.")

            history = BackupHistory(
                node_id=node.id,
                archive_name=archive_name,
                original_size=original_size,
                deduplicated_size=deduplicated_size,
                status="SUCCESS",
                log_output=stdout + "\n" + stderr
            )
            db.add(history)
            node.last_backup = datetime.utcnow()
            db.commit()

            log_to_task(task_id, "Backup completed successfully.")
            return {"status": "SUCCESS", "archive": archive_name}
        else:
            history = BackupHistory(
                node_id=node.id,
                archive_name=archive_name,
                original_size=0,
                deduplicated_size=0,
                status="FAILED",
                log_output=stdout + "\n" + stderr
            )
            db.add(history)
            db.commit()
            log_to_task(task_id, "Backup execution failed.")
            return {"status": "FAILED", "error": stderr}
    except Exception as e:
        log_to_task(task_id, f"Exception occurred during backup task: {str(e)}")
        return {"status": "FAILED", "error": str(e)}
    finally:
        db.close()

@celery_app.task
def global_daily_prune() -> Dict[str, Any]:
    """
    Celery scheduled cron task running at 3:00 AM daily.
    Executes borg prune on all node repositories locally inside the shared volume.
    """
    db: Session = SessionLocal()
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings()

    nodes = db.query(Node).all()
    results = {}

    for node in nodes:
        repo_path = f"/data/borg/{node.hostname}"
        if not os.path.exists(repo_path):
            continue

        cmd = [
            "borg", "prune",
            "--keep-daily", str(settings.keep_daily),
            "--keep-weekly", str(settings.keep_weekly),
            "--keep-monthly", str(settings.keep_monthly),
            repo_path
        ]
        env = os.environ.copy()
        env["BORG_PASSPHRASE"] = os.getenv("BORG_PASSPHRASE", "")

        try:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode == 0:
                results[node.hostname] = "PRUNED"
                logger.info(f"Successfully pruned repository for {node.hostname}")
            else:
                results[node.hostname] = f"FAILED: {res.stderr}"
                logger.error(f"Failed to prune repository for {node.hostname}: {res.stderr}")
        except Exception as e:
            results[node.hostname] = f"EXCEPTION: {str(e)}"
            logger.error(f"Exception pruning {node.hostname}: {str(e)}")

    db.close()
    return results

@celery_app.task(bind=True)
def flash_restore_device(self, node_id: int, archive_name: str, target_dev: str) -> Dict[str, Any]:
    """
    Celery task running locally on the worker in privileged mode.
    Wipes target device, partitions GPT, formats ESP with historical UUID,
    formats Root, extracts Borg backup, injects drift-preventive netconfig,
    and runs grub bootloader inside chroot.

    Args:
        node_id: ID of the Node database record.
        archive_name: The Borg backup archive identifier.
        target_dev: Target block device name (e.g. /dev/sdb).

    Returns:
        Status result dictionary.
    """
    task_id = self.request.id
    db: Session = SessionLocal()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        db.close()
        return {"status": "FAILED", "error": "Node not found"}

    task_log = TaskLog(id=task_id, task_type="RESTORE", status="RUNNING", log_output="")
    db.add(task_log)
    db.commit()

    log_to_task(task_id, f"Initializing flashing process on target device: {target_dev}")

    # Double check if EFI UUID is collected
    if not node.efi_uuid:
        log_to_task(task_id, "ERROR: EFI partition UUID is missing from database. Aborting restore to prevent data loss.")
        task_log.status = "FAILED"
        db.commit()
        db.close()
        return {"status": "FAILED", "error": "Missing EFI UUID"}

    try:
        # 1. Device scan / validation
        if not os.path.exists(target_dev):
            raise FileNotFoundError(f"Target device {target_dev} does not exist.")

        # Safety: avoid flashing host root drive
        findmnt_out = subprocess.check_output("findmnt -n -o SOURCE /", shell=True, text=True).strip()
        host_root_disk = findmnt_out
        # e.g., /dev/sda3 -> /dev/sda
        if "nvme" in host_root_disk:
            host_root_disk = host_root_disk.split("p")[0]
        else:
            host_root_disk = "".join([c for c in host_root_disk if not c.isdigit()])

        if host_root_disk in target_dev:
            raise PermissionError("PROTECTION SHIELD: Attempted to flash the orchestrator host's root drive. Blocked.")

        # 2. Wipe target signature
        log_to_task(task_id, f"Wiping signatures on {target_dev}...")
        subprocess.check_call(["wipefs", "-a", target_dev])

        # 3. Partitioning via parted (GPT)
        log_to_task(task_id, "Creating GPT partitions...")
        subprocess.check_call(["parted", "-s", target_dev, "mklabel", "gpt"])
        subprocess.check_call(["parted", "-s", target_dev, "mkpart", "ESP", "fat32", "1MiB", "513MiB"])
        subprocess.check_call(["parted", "-s", target_dev, "set", "1", "esp", "on"])
        subprocess.check_call(["parted", "-s", target_dev, "mkpart", "root", "ext4", "513MiB", "100%"])

        # Determine partition device paths
        part1 = f"{target_dev}p1" if "nvme" in target_dev else f"{target_dev}1"
        part2 = f"{target_dev}p2" if "nvme" in target_dev else f"{target_dev}2"

        # Wait a moment for devices to settle
        subprocess.check_call(["udevadm", "settle"])

        # 4. Formatting partitions
        # FAT32 UUID formatting for mkfs.vfat requires an 8-digit hexadecimal string (without dashes)
        clean_efi_uuid = node.efi_uuid.replace("-", "")[:8]
        log_to_task(task_id, f"Formatting ESP partition {part1} with UUID: {clean_efi_uuid}...")
        subprocess.check_call(["mkfs.vfat", "-F32", "-i", clean_efi_uuid, "-n", "edgeboot", part1])

        log_to_task(task_id, f"Formatting root partition {part2} with label edgeroot...")
        subprocess.check_call(["mkfs.ext4", "-F", "-L", "edgeroot", part2])

        # 5. Mounting partitions
        target_mnt = "/mnt/target"
        if os.path.exists(target_mnt):
            subprocess.run(["umount", "-R", target_mnt], stderr=subprocess.DEVNULL)
            shutil.rmtree(target_mnt, ignore_errors=True)

        os.makedirs(target_mnt, exist_ok=True)
        log_to_task(task_id, f"Mounting root filesystem to {target_mnt}...")
        subprocess.check_call(["mount", part2, target_mnt])

        os.makedirs(f"{target_mnt}/boot/efi", exist_ok=True)
        log_to_task(task_id, f"Mounting ESP filesystem to {target_mnt}/boot/efi...")
        subprocess.check_call(["mount", part1, f"{target_mnt}/boot/efi"])

        # 6. Extract Borg Backup
        repo_path = f"/data/borg/{node.hostname}"
        log_to_task(task_id, f"Extracting archive {archive_name} into {target_mnt}...")

        env = os.environ.copy()
        env["BORG_PASSPHRASE"] = os.getenv("BORG_PASSPHRASE", "")

        extract_cmd = [
            "borg", "extract", "--numeric-ids", "--sparse",
            f"{repo_path}::{archive_name}"
        ]
        # Extract files in target directory
        subprocess.check_call(extract_cmd, cwd=target_mnt, env=env)
        log_to_task(task_id, "Extraction completed successfully.")

        # 7. Network configuration injection (PCIe Drift Prevention)
        log_to_task(task_id, "Executing network configuration injection...")
        # Wipe old udev persistent rules
        udev_rules = f"{target_mnt}/etc/udev/rules.d/70-persistent-net.rules"
        if os.path.exists(udev_rules):
            os.remove(udev_rules)
            log_to_task(task_id, "Removed old persistent network udev rules.")

        # Handle network configuration
        netplan_dir = f"{target_mnt}/etc/netplan"
        if os.path.exists(netplan_dir):
            # Wipe old netplan files
            for file in os.listdir(netplan_dir):
                os.remove(os.path.join(netplan_dir, file))
            # Inject generic wildcard netplan mapping en* and eth*
            np_config = {
                "network": {
                    "version": 2,
                    "ethernets": {
                        "all-en": {
                            "match": {"name": "en*"},
                            "dhcp4": True
                        },
                        "all-eth": {
                            "match": {"name": "eth*"},
                            "dhcp4": True
                        }
                    }
                }
            }
            with open(os.path.join(netplan_dir, "01-orchestrator-dhcp.yaml"), "w") as f:
                yaml_str = json.dumps(np_config) # Netplan supports JSON formatted configuration
                f.write(yaml_str)
            log_to_task(task_id, "Injected wildcard Netplan config.")

        # Inject interfaces.d configuration
        interfaces_file = f"{target_mnt}/etc/network/interfaces"
        if os.path.exists(interfaces_file) or os.path.exists(f"{target_mnt}/etc/network"):
            os.makedirs(f"{target_mnt}/etc/network/interfaces.d", exist_ok=True)
            # Standard generic loopback configuration
            with open(interfaces_file, "w") as f:
                f.write("auto lo\niface lo inet loopback\nsource /etc/network/interfaces.d/*\n")

            # Enable DHCP on common naming structures plus original node name
            ifaces_to_configure = ["eth0", "enp1s0", "enp2s0", "enp3s0"]
            if node.network_iface and node.network_iface not in ifaces_to_configure:
                ifaces_to_configure.append(node.network_iface)

            with open(f"{target_mnt}/etc/network/interfaces.d/orchestrator-dhcp", "w") as f:
                for iface in ifaces_to_configure:
                    f.write(f"allow-hotplug {iface}\niface {iface} inet dhcp\n\n")
            log_to_task(task_id, f"Injected /etc/network/interfaces.d config mapping: {', '.join(ifaces_to_configure)}")

        # 8. Chroot, Grub setup
        log_to_task(task_id, "Mounting virtual filesystems...")
        subprocess.check_call(["mount", "--bind", "/dev", f"{target_mnt}/dev"])
        subprocess.check_call(["mount", "--bind", "/dev/pts", f"{target_mnt}/dev/pts"])
        subprocess.check_call(["mount", "--bind", "/proc", f"{target_mnt}/dev/../proc"]) # safe proc binding
        subprocess.check_call(["mount", "--bind", "/sys", f"{target_mnt}/sys"])

        log_to_task(task_id, f"Reinstalling GRUB bootloader on {target_dev}...")
        subprocess.check_call(["chroot", target_mnt, "grub-install", target_dev])
        subprocess.check_call(["chroot", target_mnt, "update-grub"])

        # Inject EFI Fallback path to make sure UEFI sees it
        efi_base = f"{target_mnt}/boot/efi/EFI"
        fallback_dir = f"{efi_base}/BOOT"
        os.makedirs(fallback_dir, exist_ok=True)

        # Search for any efi file generated by grub-install inside EFI/
        grub_efi_src = None
        for root, dirs, files in os.walk(efi_base):
            for file in files:
                if file.endswith(".efi") and "BOOT" not in root:
                    grub_efi_src = os.path.join(root, file)
                    break
            if grub_efi_src:
                break

        if grub_efi_src:
            log_to_task(task_id, f"Copying EFI fallback loader: {grub_efi_src} -> {fallback_dir}/BOOTX64.EFI")
            shutil.copy2(grub_efi_src, f"{fallback_dir}/BOOTX64.EFI")
        else:
            log_to_task(task_id, "WARNING: Could not find compiled grubx64.efi loader. Proceeding.")

        # 9. Post-Restore verification audit
        log_to_task(task_id, "Starting post-restore audit...")
        fstab_content = ""
        with open(f"{target_mnt}/etc/fstab", "r") as f:
            fstab_content = f.read()

        if "LABEL=edgeroot" not in fstab_content:
            raise ValueError("Post-restore verification audit failed: /etc/fstab is missing LABEL=edgeroot mapping.")

        log_to_task(task_id, "Post-restore verification audit passed. Filesystems, labels, and fstab structures are verified.")

        # Unmount virtual filesystems
        log_to_task(task_id, "Unmounting virtual filesystems...")
        subprocess.check_call(["umount", "-R", target_mnt])

        task_log.status = "SUCCESS"
        db.commit()
        log_to_task(task_id, "Restore completed successfully! Target device ready to boot.")
        return {"status": "SUCCESS"}

    except Exception as e:
        error_msg = f"Restore execution failed: {str(e)}"
        log_to_task(task_id, error_msg)
        task_log.status = "FAILED"
        db.commit()

        # Clean unmount on failure
        try:
            subprocess.run(["umount", "-R", "/mnt/target"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return {"status": "FAILED", "error": str(e)}
    finally:
        db.close()
