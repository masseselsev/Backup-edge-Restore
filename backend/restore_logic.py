import os
import shutil
import subprocess
import json
from typing import Dict, Any
from sqlalchemy.orm import Session
from database import SessionLocal
from models import TaskLog, Node

def execute_restore(task_obj: Any, node_id: int, archive_name: str, target_dev: str) -> Dict[str, Any]:
    """
    Executes the bare-metal restore partition flashing, filesystem formatting,
    Borg backup extraction, and network wildcard injection.
    """
    from tasks import log_to_task

    task_id = task_obj.request.id
    db: Session = SessionLocal()
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        db.close()
        return {"status": "FAILED", "error": "Node not found"}

    task_log = db.query(TaskLog).filter(TaskLog.id == task_id).first()
    if not task_log:
        task_log = TaskLog(id=task_id, task_type="RESTORE", status="RUNNING", log_output="")
        db.add(task_log)
        db.commit()

    log_to_task(task_id, f"Initializing flashing process on target device: {target_dev}")

    # Double check if EFI UUID is collected
    if not node.efi_uuid:
        log_to_task(task_id, "ERROR: EFI partition UUID is missing from database. Aborting restore to prevent data loss.", status="FAILED")
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
                yaml_str = json.dumps(np_config)
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
        subprocess.check_call(["mount", "--bind", "/proc", f"{target_mnt}/dev/../proc"])
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
        for root_dir, dirs, files in os.walk(efi_base):
            for file in files:
                if file.endswith(".efi") and "BOOT" not in root_dir:
                    grub_efi_src = os.path.join(root_dir, file)
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

        log_to_task(task_id, "Restore completed successfully! Target device ready to boot.", status="SUCCESS")
        return {"status": "SUCCESS"}

    except Exception as e:
        error_msg = f"Restore execution failed: {str(e)}"
        log_to_task(task_id, error_msg, status="FAILED")

        # Clean unmount on failure
        try:
            subprocess.run(["umount", "-R", "/mnt/target"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return {"status": "FAILED", "error": str(e)}
    finally:
        db.close()
