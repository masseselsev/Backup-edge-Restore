from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from version import VERSION

router = APIRouter(prefix="/api")

@router.get("/version")
def get_version():
    """
    Returns the current application version.
    """
    return {"version": VERSION, "is_kiosk": False}


@router.get("/settings", response_model=schemas.SettingsResponse)
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


@router.post("/settings", response_model=schemas.SettingsResponse)
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
    settings.orchestrator_ip = payload.orchestrator_ip
    settings.timezone = payload.timezone
    db.commit()
    return settings
