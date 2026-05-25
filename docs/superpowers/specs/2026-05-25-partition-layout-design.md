# Spec: Dynamic Adaptive Disk Partitioning & Restore Engine

This specification describes the dynamic adaptive disk partitioning, formatting, mounting, and `/etc/fstab` reconstruction engine to support any hardware layout on fleet edge nodes.

## Architecture

We replace hardcoded 5-partition structures with a dynamic database-backed JSON schema captured at bootstrap/auto-prepare time.

### 1. Database Model Changes

We add a new column to the `Node` model:
- `partition_layout`: `JSON` type, default `None` (Nullable).

### 2. Auto-Prepare Partition Discovery

During the execution of `prepare.yml` (and auto-detection in `bootstrap.yml`), we run:
```bash
lsblk -J -b -o NAME,TYPE,FSTYPE,SIZE,MOUNTPOINT,LABEL,UUID
```
And parse the JSON response in the orchestrator:
1. Filter block devices belonging to the same physical disk as the `/` root filesystem.
2. Collect partitions that have non-empty mount points (`/`, `/boot`, `/boot/efi`, etc.).
3. Serialize them into a sorted array based on their physical partition suffix (e.g. `p1`, `p2`, `p3...`).
4. Save the schema to `Node.partition_layout` in the database.

### 3. Dynamic Bare-Metal Restore

During restore (`restore_logic.py`):
1. **Partitioning**: Partition the target device sequentially based on the physical index order (`p1`, `p2`, `p3...`) from the collected `partition_layout` schema.
   - Calculate sizes in `MiB`.
   - The last physical partition dynamically consumes `100%` of the remaining disk space.
   - Flag the partition mounting at `/boot/efi` with the `esp on` flag.
2. **Formatting**: Format partitions based on their `fstype` and `label`.
   - For `vfat` (EFI), strip hyphens from the UUID (e.g. `458C-37BB` to `458C37BB`) and format with `mkfs.vfat -i`.
   - Format ext partitions with `mkfs.ext2/3/4` using their respective labels.
3. **Mounting**: Mount partitions hierarchically under `/mnt/target` sorted by their path component depth:
   ```python
   import pathlib
   partitions.sort(key=lambda x: len(pathlib.PurePosixPath(x["mount"]).parts))
   ```
4. **fstab Generation**: Generate target `/mnt/target/etc/fstab` dynamically.
   - Map `/boot/efi` by its dynamic `UUID={node.efi_uuid}`.
   - Map other partitions by their `LABEL={label}` or `UUID={uuid}`.
