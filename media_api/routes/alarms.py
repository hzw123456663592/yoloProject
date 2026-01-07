from __future__ import annotations
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from common.settings import load_settings
from common.schemas import AlarmItem, AlarmListResponse
from media_api.services.state import stream_manager

router = APIRouter()
settings = load_settings()


@router.get("/alarms", response_model=AlarmListResponse)
def list_alarms(limit: int = 50):
    """列出最近的告警。"""
    store = stream_manager.alarm_store
    rows = store.list_alarms(limit=limit)
    items: List[AlarmItem] = [
        AlarmItem(
            alarm_id=row["alarm_id"],
            camera_id=row["camera_id"],
            rtsp_url=row["rtsp_url"],
            timestamp=row["timestamp"],
            msg=row.get("msg", ""),
            snapshot_url=row.get("snapshot_url"),
            clip_url=row.get("clip_url"),
            extra=row.get("extra", {}),
        )
        for row in rows
    ]
    return AlarmListResponse(items=items)


@router.get("/alarms/{alarm_id}", response_model=AlarmItem)
def get_alarm(alarm_id: str):
    store = stream_manager.alarm_store
    row = store.get_alarm(alarm_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return AlarmItem(
        alarm_id=row["alarm_id"],
        camera_id=row["camera_id"],
        rtsp_url=row["rtsp_url"],
        timestamp=row["timestamp"],
        msg=row.get("msg", ""),
        snapshot_url=row.get("snapshot_url"),
        clip_url=row.get("clip_url"),
        extra=row.get("extra", {}),
    )


@router.get("/snapshots/{date_folder}/{name}")
def get_snapshot(date_folder: str, name: str):
    p = Path(settings.storage["alarms_dir"]) / date_folder / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/jpeg")


@router.get("/clips/{date_folder}/{name}")
def get_clip(date_folder: str, name: str):
    p = Path(settings.storage["clips_dir"]) / date_folder / name
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="video/mp4")
