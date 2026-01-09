from __future__ import annotations

from fastapi import APIRouter, HTTPException

from common.config_models import SystemConfig
from common.config_store import load_system_config, save_system_config
from media_api.services.state import stream_manager

router = APIRouter()


@router.get("/system", response_model=SystemConfig)
def get_system_config():
    return load_system_config()


@router.put("/system", response_model=SystemConfig)
def update_system_config(cfg: SystemConfig):
    try:
        save_system_config(cfg)
        stream_manager.update_streams(cfg.streams)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return cfg
