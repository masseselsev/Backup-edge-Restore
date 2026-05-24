# Borg Backup & Bare-Metal Restore Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready Borg Backup and Bare-Metal Restore Orchestrator for 200+ Debian-based edge nodes.

**Architecture:** A multi-container Docker Compose application comprising a React frontend (Nginx), a FastAPI backend, a Celery task worker (privileged host-device access), a Redis broker, and a dedicated Borg SSH server container mounting a shared Postgres database.

**Tech Stack:** Python (FastAPI, SQLAlchemy, Celery, Ansible Runner), PostgreSQL, Redis, Docker, React (TypeScript, Tailwind, Lucide Icons).

---

## Proposed Changes

### Task 1: Repository Guidelines & Project Scaffolding

Set up the project rules file `GEMINI.md` and build the containerized infrastructure with Docker Compose.

**Files:**
- Create: `GEMINI.md`
- Create: `docker-compose.yml`
- Create: `docker/backend/Dockerfile`
- Create: `docker/borg/Dockerfile`
- Create: `docker/frontend/Dockerfile`
- Create: `.env`

- [ ] **Step 1.1: Create `GEMINI.md`**
  Write the AI coding standards, limits, and repo map.
  ```markdown
  # GEMINI AI Manifest & Repository Rules

  ## Tech Stack
  - Backend: Python 3.11, FastAPI, SQLAlchemy, Alembic, Celery, Ansible Runner
  - Database: PostgreSQL
  - Task Queue: Redis
  - Frontend: React, TypeScript, Tailwind CSS, Lucide Icons
  - Deployment: Docker Compose

  ## Coding Guidelines
  - **Strict Python Type Hinting**: Always use Pydantic models for request/response serialization.
  - **Maximum File Size**: No single file must exceed 500 lines. Split routers, tasks, and components when they grow.
  - **Database Migrations**: Always use Alembic migrations for DB changes. Do not modify database schemas directly.
  - **Secrets Management**: Read Borg Passphrase (`BORG_PASSPHRASE`) and Database credentials exclusively from environment variables/`.env`. Never store them in DB or VCS.
  ```

- [ ] **Step 1.2: Create the `.env` file**
  ```env
  POSTGRES_USER=postgres
  POSTGRES_PASSWORD=securepassword
  POSTGRES_DB=borg_orchestrator
  REDIS_URL=redis://redis:6379/0
  BORG_PASSPHRASE=verysecureborgpassphrase
  DATABASE_URL=postgresql://postgres:securepassword@db:5432/borg_orchestrator
  ```

- [ ] **Step 1.3: Create Backend & Borg Dockerfiles**
  `docker/backend/Dockerfile`:
  ```dockerfile
  FROM python:3.11-slim
  RUN apt-get update && apt-get install -y \
      ssh openssh-client rsync curl parted wipefs dosfstools e2fsprogs systemd \
      && rm -rf /var/lib/apt/lists/*
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install -r requirements.txt
  COPY . .
  ```
  `docker/borg/Dockerfile`:
  ```dockerfile
  FROM debian:bookworm-slim
  RUN apt-get update && apt-get install -y \
      openssh-server borgbackup \
      && rm -rf /var/lib/apt/lists/*
  RUN mkdir /var/run/sshd && mkdir -p /data/borg
  RUN useradd -m -d /home/borg -s /bin/bash borg
  EXPOSE 22
  CMD ["/usr/sbin/sshd", "-D"]
  ```

- [ ] **Step 1.4: Create the `docker-compose.yml`**
  ```yaml
  version: '3.8'
  services:
    db:
      image: postgres:15-alpine
      environment:
        POSTGRES_USER: ${POSTGRES_USER}
        POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
        POSTGRES_DB: ${POSTGRES_DB}
      volumes:
        - pg-data:/var/lib/postgresql/data
    redis:
      image: redis:7-alpine
    backend:
      build:
        context: ./backend
        dockerfile: ../docker/backend/Dockerfile
      ports:
        - "7777:7777"
      environment:
        DATABASE_URL: ${DATABASE_URL}
        REDIS_URL: ${REDIS_URL}
      volumes:
        - ./backend:/app
        - borg-data:/data/borg
    worker:
      build:
        context: ./backend
        dockerfile: ../docker/backend/Dockerfile
      privileged: true
      network_mode: host
      environment:
        DATABASE_URL: ${DATABASE_URL}
        REDIS_URL: ${REDIS_URL}
        BORG_PASSPHRASE: ${BORG_PASSPHRASE}
      volumes:
        - ./backend:/app
        - /dev:/dev
        - borg-data:/data/borg
    borg-server:
      build:
        context: .
        dockerfile: docker/borg/Dockerfile
      ports:
        - "12345:22"
      volumes:
        - borg-data:/data/borg
        - ssh-keys:/home/borg/.ssh
  volumes:
    pg-data:
    borg-data:
    ssh-keys:
  ```

- [ ] **Step 1.5: Commit changes**
  ```bash
  git add GEMINI.md docker-compose.yml docker/ .env
  git commit -m "chore: scaffold docker setup and repo rules"
  ```

---

### Task 2: Database Models & Alembic Migrations

Configure SQLAlchemy models and Alembic migrations.

**Files:**
- Create: `backend/database.py`
- Create: `backend/models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`

- [ ] **Step 2.1: Write `backend/database.py`**
  Provide session factories and base classes.
  ```python
  import os
  from sqlalchemy import create_engine
  from sqlalchemy.ext.declarative import declarative_base
  from sqlalchemy.orm import sessionmaker

  DATABASE_URL = os.getenv("DATABASE_URL")
  engine = create_engine(DATABASE_URL)
  SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
  Base = declarative_base()

  def get_db():
      db = SessionLocal()
      try:
          yield db
      finally:
          db.close()
  ```

- [ ] **Step 2.2: Write models in `backend/models.py`**
  Include `Settings`, `Node`, `BackupHistory`, `TaskLog`. Ensure `Node.efi_uuid` is present.
  ```python
  from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, ForeignKey
  from sqlalchemy.sql import func
  from database import Base

  class Settings(Base):
      __tablename__ = 'settings'
      id = Column(Integer, primary_key=True)
      borg_ssh_port = Column(Integer, default=12345)
      borg_repo_path = Column(String, default='/data/borg')
      keep_daily = Column(Integer, default=7)
      keep_weekly = Column(Integer, default=4)
      keep_monthly = Column(Integer, default=6)
      global_exclusions = Column(Text, default='/dev/*,/proc/*,/sys/*,/run/*,/mnt/*')

  class Node(Base):
      __tablename__ = 'nodes'
      id = Column(Integer, primary_key=True)
      hostname = Column(String, unique=True, nullable=False)
      ip_address = Column(String, unique=True, nullable=False)
      ssh_port = Column(Integer, default=22)
      status = Column(String, default='NEEDS_BOOTSTRAP') # OFFLINE, NEEDS_BOOTSTRAP, NEEDS_FIX, READY
      last_backup = Column(DateTime, nullable=True)
      disk_type = Column(String, default='UNKNOWN') # SATA, NVME, UNKNOWN
      network_iface = Column(String, nullable=True)
      ssh_pub_key = Column(Text, nullable=True)
      efi_uuid = Column(String, nullable=True)

  class BackupHistory(Base):
      __tablename__ = 'backup_history'
      id = Column(Integer, primary_key=True)
      node_id = Column(Integer, ForeignKey('nodes.id'))
      archive_name = Column(String, unique=True)
      timestamp = Column(DateTime, default=func.now())
      original_size = Column(BigInteger)
      deduplicated_size = Column(BigInteger)
      status = Column(String)
      log_output = Column(Text, nullable=True)

  class TaskLog(Base):
      __tablename__ = 'task_logs'
      id = Column(String, primary_key=True)
      task_type = Column(String) # BOOTSTRAP, PREPARE, BACKUP, RESTORE
      status = Column(String, default='PENDING') # PENDING, RUNNING, SUCCESS, FAILED
      created_at = Column(DateTime, default=func.now())
      updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
      log_output = Column(Text, default='')
  ```

- [ ] **Step 2.3: Generate initial migrations**
  Run: `cd backend && alembic init alembic`
  Modify `backend/alembic/env.py` to target metadata.
  Run: `alembic revision --autogenerate -m "initial_schema"`
  Run: `alembic upgrade head`

- [ ] **Step 2.4: Commit migrations**
  ```bash
  git add backend/database.py backend/models.py backend/alembic.ini backend/alembic/
  git commit -m "feat: add db models and initial migration"
  ```

---

### Task 3: Ansible Auto-Provisioning & Auto-Prepare

Write idempotent playbooks to bootstrap and label nodes, storing partitions and EFI UUID.

**Files:**
- Create: `backend/playbooks/bootstrap.yml`
- Create: `backend/playbooks/prepare.yml`
- Create: `backend/ansible_utils.py`

- [ ] **Step 3.1: Write the `bootstrap.yml` playbook**
  Escalates to root to install `borgbackup`, create `borg` user, generate SSH keys, and fetch pubkey.
  ```yaml
  ---
  - name: Bootstrap Edge Node
    hosts: all
    become: yes
    tasks:
      - name: Install dependencies
        apt:
          name: [borgbackup, parted, udev]
          state: present
          update_cache: yes
      - name: Create borg system user
        user:
          name: borg
          shell: /bin/bash
          create_home: yes
      - name: Generate SSH key for borg user
        user:
          name: borg
          generate_ssh_key: yes
          ssh_key_type: ed25519
          ssh_key_file: .ssh/id_ed25519
      - name: Read generated public key
        slurp:
          src: /home/borg/.ssh/id_ed25519.pub
        register: pubkey
      - name: Return public key to orchestrator
        debug:
          msg: "SSH_KEY: {{ pubkey['content'] | b64decode }}"
  ```

- [ ] **Step 3.2: Write the `prepare.yml` playbook**
  Wipes old configurations, detects EFI UUID, disk details, writes filesystem labels, and configures `/etc/fstab` with fallback mechanisms.
  ```yaml
  ---
  - name: Auto-Prepare (Fix Labels)
    hosts: all
    become: yes
    tasks:
      - name: Backup remote fstab
        copy:
          src: /etc/fstab
          dest: /etc/fstab.bak
          remote_src: yes
      - name: Detect active disk type and EFI partition UUID
        shell: |
          root_dev=$(findmnt -n -o SOURCE /)
          parent_disk=$(lsblk -no PKNAME $root_dev)
          efi_part=$(lsblk -lo NAME,FSTYPE $parent_disk | grep vfat | awk '{print $1}')
          efi_uuid=$(blkid -s UUID -o value /dev/$efi_part)
          echo "DISK_TYPE: $(cat /sys/block/$parent_disk/queue/rotational)"
          echo "EFI_UUID: $efi_uuid"
          echo "INTERFACE: $(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')"
        register: disk_details
      - name: Return details to orchestrator
        debug:
          msg: "{{ disk_details.stdout }}"
      - name: Apply filesystem labels
        shell: |
          tune2fs -L edgeroot $(findmnt -n -o SOURCE /)
          # Label ESP boot partition
          fatlabel $(findmnt -n -o SOURCE /boot/efi) edgeboot || dosfslabel $(findmnt -n -o SOURCE /boot/efi) edgeboot
        ignore_errors: yes
      - name: Rewrite fstab with labels
        copy:
          dest: /etc/fstab
          content: |
            LABEL=edgeroot / ext4 defaults 0 1
            LABEL=edgeboot /boot/efi vfat defaults 0 2
      - name: Update initramfs & GRUB
        shell: |
          update-initramfs -u
          update-grub
  ```

- [ ] **Step 3.3: Commit playbooks**
  ```bash
  git add backend/playbooks/
  git commit -m "feat: add bootstrap and auto-prepare ansible playbooks"
  ```

---

### Task 4: FastAPI APIs & Celery Queue Tasks

Build RESTful endpoints and core backup/restore workers.

**Files:**
- Create: `backend/tasks.py`
- Create: `backend/main.py`

- [ ] **Step 4.1: Write Celery tasks (`backend/tasks.py`)**
  Implement task logging, running backups, restoration steps, and global cron-pruning.
  ```python
  import subprocess
  import os
  from celery import Celery
  from database import SessionLocal
  from models import TaskLog, Node, BackupHistory

  celery_app = Celery("tasks", broker=os.getenv("REDIS_URL"), backend=os.getenv("REDIS_URL"))

  @celery_app.task(bind=True)
  def run_backup(self, node_id: int):
      db = SessionLocal()
      node = db.query(Node).filter(Node.id == node_id).first()
      # Execute ssh backup command pushing to central SSH Borg repository
      # Save stats to BackupHistory
      pass

  @celery_app.task
  def global_daily_prune():
      # Runs daily at 3:00 AM. Acquires exclusive lock on repo and prunes.
      pass

  @celery_app.task(bind=True)
  def flash_restore_device(self, node_id: int, snapshot_id: str, target_dev: str):
      # Wipe target_dev, partition (GPT), mkfs.vfat with efi_uuid, mkfs.ext4 with labels
      # Mount and borg extract, rewrite network interfaces, chroot grub install, and verify.
      pass
  ```

- [ ] **Step 4.2: Build APIs in `backend/main.py`**
  ```python
  from fastapi import FastAPI, Depends
  from sqlalchemy.orm import Session
  from database import get_db
  from models import Node, Settings, TaskLog

  app = FastAPI()

  @app.post("/api/nodes")
  def add_node(hostname: str, ip_address: str, db: Session = Depends(get_db)):
      # Add new node and trigger bootstrap task
      pass

  @app.post("/api/restore")
  def trigger_restore(node_id: int, snapshot: str, target_dev: str):
      # Validate target_dev, disk type mismatch warning, run flash task
      pass
  ```

---

### Task 5: React SPA Frontend

Write the frontend interface with tabs for Fleet, History, Flasher, and Settings.

**Files:**
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/components/FlasherConsole.tsx`
- Create: `frontend/src/components/FleetDashboard.tsx`

- [ ] **Step 5.1: Create Frontend Dashboard & Flasher console**
  Ensure real-time polling from `/api/tasks/<task_id>/logs` to display execution outputs.
  Create custom warnings when flashing partition mismatches occur.

---

## Verification Plan

### Automated Tests
- Run Pytest to verify DB operations: `pytest tests/`
- Run local Celery mock tasks: `pytest tests/test_tasks.py`

### Manual Verification
- Test bootstrap playbook on local test container.
- Use loopback devices (`/dev/loop0`) to mock SATA/NVMe targets for Module 5 flashing logic verification.
