"""Data ingestion API — CSV upload for sensor and maintenance data."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.ingestion.csv_ingestion import ingest_sensor_csv, ingest_maintenance_csv

router = APIRouter()

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/sensors")
async def ingest_sensors(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a sensor/HUMS CSV file. Returns detailed validation and ingestion results."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = ingest_sensor_csv(content, file.filename, db)
    status_code = 200 if result.success else 422
    return result.to_dict()


@router.post("/maintenance")
async def ingest_maintenance(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Upload a maintenance records CSV file. Returns detailed validation and ingestion results."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    result = ingest_maintenance_csv(content, file.filename, db)
    return result.to_dict()
