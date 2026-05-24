# Borg Backup & Bare-Metal Restore Orchestrator - Design Specification

This document details the system design for the Borg Backup & Bare-Metal Restore Orchestrator, designed to manage backups and perform bare-metal restores for a fleet of 200+ Debian-based edge nodes.

## 1. System Architecture

The application will run inside a multi-container Docker environment:

```
                                    +-----------------------+
                                    |    React Frontend     |
                                    |   (SPA via Nginx)     |
                                    +-----------+-----------+
                                                | HTTP (Port 7777)
                                                v
                                    +-----------------------+
                                    |    FastAPI Backend    |
                                    +-----+-----------+-----+
                                          |           |
                     Read/Write SQLite DB |           | Enqueue Tasks
                                          v           v
                                   +------------+ +-------+
                                   | SQLite DB  | | Redis |
                                   +------------+ +---+---+
                                                      |
                                                      v Task Execution
                                              +---------------+
                                              | Celery Worker |
                                              +-------+-------+
                                                      |
                                                      | Read/Write
                                                      v
                                            +------------------+
                                            | Shared Borg Repo |
                                            |  (/data/borg)    |
                                            +--------+---------+
                                                     ^
                                                     | Backup Pull/Push via SSH
                                                     v
                                            +------------------+
                                            |  Borg SSH Server |
                                            |   (Port 12345)   |
                                            +------------------+
```

### Components
1. **`web-frontend`**:
   - Single Page Application built with React, TypeScript, Tailwind CSS, and Lucide Icons.
   - Served via Nginx on port 7777, proxying API requests (`/api/*`) to the backend.
2. **`fastapi-backend`**:
   - Python-based FastAPI web framework.
   - Exposes RESTful API endpoints for Node management, backup scheduling, restore operations, global configuration settings, and task logging.
   - Manages persistence using PostgreSQL via SQLAlchemy and Alembic migrations.
3. **`celery-worker`**:
   - Background worker task queue.
   - Runs in `--privileged` mode with `/dev` mounted from the host to scan, format, and flash physical disk drives (SATA/NVMe).
   - Mounts the shared Borg repository `/data/borg` to extract archives locally.
   - Executes Ansible playbooks via `ansible-runner` or subprocesses.
4. **`redis`**:
   - In-memory message broker for Celery queue management.
5. **`borg-server`**:
   - Dedicated SSH container running `borgbackup`.
   - Exposes port `12345` (mapped to host) for remote nodes to connect and push backup archives.
   - Restricts commands in `authorized_keys` to ensure nodes can only perform safe backup tasks matching their identifier.

---

## 2. Database Schema & Persistence

Managed with SQLAlchemy, Alembic, and PostgreSQL.

### `Settings`
- `id`: Integer (Primary Key)
- `borg_ssh_port`: Integer (Default: `12345`)
- `borg_repo_path`: String (Default: `/data/borg`)
- `keep_daily`: Integer (Default: `7`)
- `keep_weekly`: Integer (Default: `4`)
- `keep_monthly`: Integer (Default: `6`)
- `global_exclusions`: Text (Default: `/dev/*,/proc/*,/sys/*,/run/*,/mnt/*`)
- Note: Borg passphrase (`BORG_PASSPHRASE`) is NOT stored in the database. It is read exclusively from the environment via a `.env` file injected into the FastAPI and Celery worker containers.

### `Node`
- `id`: Integer (Primary Key)
- `hostname`: String (Unique)
- `ip_address`: String (Unique)
- `ssh_port`: Integer (Default: `22`)
- `status`: String (`OFFLINE`, `NEEDS_BOOTSTRAP`, `NEEDS_FIX`, `READY`)
- `last_backup`: DateTime (Nullable)
- `disk_type`: String (`SATA`, `NVME`, `UNKNOWN`)
- `network_iface`: String (Nullable)
- `ssh_pub_key`: Text (Nullable, node's Borg key)
- `efi_uuid`: String (Nullable) — Collected during auto-prepare, used for bootloader formatting

### `BackupHistory`
- `id`: Integer (Primary Key)
- `node_id`: Integer (Foreign Key to `Node.id`)
- `archive_name`: String (Unique)
- `timestamp`: DateTime
- `original_size`: BigInteger (Original uncompressed/undeduplicated size)
- `deduplicated_size`: BigInteger (Deduplicated repo size)
- `status`: String (`SUCCESS`, `FAILED`)
- `log_output`: Text (Verbose logging of execution)

### `TaskLog`
- `id`: String (UUID/Primary Key)
- `task_type`: String (`BOOTSTRAP`, `PREPARE`, `BACKUP`, `RESTORE`)
- `status`: String (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`)
- `created_at`: DateTime
- `updated_at`: DateTime
- `log_output`: Text (Appended sequentially as logs flow in)

---

## 3. Provisioning & Playbook Execution

Ansible playbooks will run with detailed logging at every stage.

### Module 2: Auto-Provisioning (Bootstrap)
- Runs via temporary user/password credentials entered in UI (deleted from memory after run).
- Installs necessary tools (`python3`, `borgbackup`).
- Creates local `borg` user on the edge node.
- Generates Ed25519 keypair for `borg` user.
- Fetches the public key to append to Orchestrator's `authorized_keys` with forced command limits:
  `command="borg serve --restrict-to-path /data/borg/<hostname>",no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 ...`
- Configures passwordless SSH control keys for management.

### Module 3: Auto-Prepare (Fstab & Labels)
- Backs up fstab to `/etc/fstab.bak`.
- Queries partitions via `lsblk` and `findmnt`.
- Detects disk type (SATA vs NVMe) and active interface name.
- Reads the UUID of the remote host's EFI/ESP partition using `blkid -s UUID -o value /dev/...` (or parsing lsblk) and saves it to `Node.efi_uuid` in the database.
- Appends filesystem labels `edgeroot`, `edgeboot`, `edgelog`, and `edgestor` to target filesystems using `e2label` or `dosfslabel`.
- Rewrites `/etc/fstab` with labels instead of UUIDs.
- Triggers `update-initramfs -u` and `update-grub`.
- Rollback: Reverts `/etc/fstab` from `/etc/fstab.bak` if errors occur.

---

## 4. Backup & Bare-Metal Restore

### Backup Schedule & Execution (Module 4)
- Triggers `borg create` on remote node pushing to Central Borg server.
- **Locking & Prune Strategy**: To avoid repository lock contention and tasks crashing during concurrent backups, `borg prune` is **removed** from the individual backup flow. Instead, a **Global Scheduled Celery Task (Cron)** runs once per day (e.g. at 3:00 AM) when no backup creation tasks are running, acquiring the exclusive lock and pruning the repositories.
- Inserts size data into `BackupHistory`.

### Bare-Metal Restore Flashing (Module 5)
- **Local Dev Scanning**: Scans `/sys/block` and filters out the host's root drive.
- **Partition & Format**:
  - Partitions via `parted` using GPT.
  - Formats ESP: Uses the stored `Node.efi_uuid` (required, aborts if missing) via `mkfs.vfat -F32 -i <EFI_UUID_HEX> -n edgeboot <target_dev_part1>` (converting UUID to hex format without dashes).
  - Formats Root: `mkfs.ext4 -L edgeroot <target_dev_part2>`.
- **Data Extract**: Mounts partitions to `/mnt/target` and runs local `borg extract`.
- **Network Injection**:
  - Wipes any old udev network persistent rules (e.g., `/etc/udev/rules.d/70-persistent-net.rules` or equivalent) on the target filesystem.
  - Injects a generic netplan or `/etc/network/interfaces` configuration that uses wildcard matching (e.g., interface name pattern `en*` or `eth*`) or matches the host interface name, to ensure PCIe drift doesn't break network boot access.
- **Bootloader**: Bind-mounts `/dev`, `/proc`, `/sys` and executes `grub-install` + `update-grub` in chroot. Copies standard EFI fallback path (`/boot/efi/EFI/BOOT/BOOTX64.EFI`).
- **Verification Audit**: Scans filesystem structure, labels, fstab, and bootloader integrity before unmounting.

---

## 5. Security Strategy

1. **Password Scoping**: Plaintext bootstrap passwords are transient and never saved to the database.
2. **Forced SSH Command Restrictions**: Remote nodes cannot run arbitrary shell commands; they are restricted strictly to `borg serve` operations inside their designated directory.
3. **Privileged Separation**: Only the Celery worker container runs with `--privileged` and `/dev` mounted. The API server does not have direct access to physical devices.
4. **Secrets Hardening**: The Borg Repository passphrase is read only from the BORG_PASSPHRASE environment variable (from `.env`), keeping it completely out of the database and VCS.
5. **Input Validation**: All incoming endpoints are strictly validated using Pydantic models. Shell arguments for execution are parameterized.

