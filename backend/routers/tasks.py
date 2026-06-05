from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas

router = APIRouter(prefix="/api/tasks")

@router.get("/{task_id}", response_model=schemas.TaskLogResponse)
def get_task_logs(task_id: str, db: Session = Depends(get_db)):
    """
    Fetches execution logs and status of a background task.
    """
    task = db.query(models.TaskLog).filter(models.TaskLog.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task
