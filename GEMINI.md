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
