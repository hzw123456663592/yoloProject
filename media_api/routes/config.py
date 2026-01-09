from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

from common.config_models import (
    AlgorithmConfig,
    StreamItem,
    StreamsConfig,
    SystemConfig,
)
from common.config_store import load_system_config, save_system_config
from media_api.services.state import stream_manager

router = APIRouter()


def _ensure_algo_exists(cfg: SystemConfig, name: str) -> None:
    if name not in cfg.algorithms:
        raise HTTPException(status_code=400, detail=f"algorithm '{name}' not found")


def _save_and_reload_streams(cfg: SystemConfig) -> None:
    save_system_config(cfg)
    stream_manager.update_streams(cfg.streams)


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


@router.get("/streams", response_model=StreamsConfig)
def get_streams():
    return load_system_config().streams


@router.post("/streams", response_model=StreamItem)
def add_stream(item: StreamItem):
    cfg = load_system_config()
    if any(s.camera_id == item.camera_id for s in cfg.streams.items):
        raise HTTPException(status_code=400, detail="camera_id already exists")
    for alg in item.algorithms:
        _ensure_algo_exists(cfg, alg)
    for override_name in item.algorithm_overrides.keys():
        _ensure_algo_exists(cfg, override_name)
    cfg.streams.items.append(item)
    _save_and_reload_streams(cfg)
    return item


@router.put("/streams/{camera_id}", response_model=StreamItem)
def update_stream(camera_id: str, item: StreamItem):
    cfg = load_system_config()
    target = next((s for s in cfg.streams.items if s.camera_id == camera_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="stream not found")
    for alg in item.algorithms:
        _ensure_algo_exists(cfg, alg)
    for override_name in item.algorithm_overrides.keys():
        _ensure_algo_exists(cfg, override_name)
    cfg.streams.items = [
        item if s.camera_id == camera_id else s for s in cfg.streams.items
    ]
    _save_and_reload_streams(cfg)
    return item


@router.delete("/streams/{camera_id}")
def delete_stream(camera_id: str):
    cfg = load_system_config()
    items = [s for s in cfg.streams.items if s.camera_id != camera_id]
    if len(items) == len(cfg.streams.items):
        raise HTTPException(status_code=404, detail="stream not found")
    cfg.streams.items = items
    _save_and_reload_streams(cfg)
    return {"camera_id": camera_id}


class AlgorithmPayload(BaseModel):
    name: str
    config: AlgorithmConfig


class AlgorithmNamePayload(BaseModel):
    name: str


@router.get("/algorithms", response_model=Dict[str, AlgorithmConfig])
def get_algorithms():
    return load_system_config().algorithms


@router.post("/algorithms", response_model=AlgorithmConfig)
def add_algorithm(payload: AlgorithmPayload):
    cfg = load_system_config()
    if payload.name in cfg.algorithms:
        raise HTTPException(status_code=400, detail="algorithm already exists")
    cfg.algorithms[payload.name] = payload.config
    save_system_config(cfg)
    return payload.config


@router.put("/algorithms", response_model=AlgorithmConfig)
def update_algorithm(payload: AlgorithmPayload):
    cfg = load_system_config()
    if payload.name not in cfg.algorithms:
        raise HTTPException(status_code=404, detail="algorithm not found")
    cfg.algorithms[payload.name] = payload.config
    save_system_config(cfg)
    return payload.config


@router.delete("/algorithms")
def delete_algorithm(payload: AlgorithmNamePayload):
    cfg = load_system_config()
    if payload.name not in cfg.algorithms:
        raise HTTPException(status_code=404, detail="algorithm not found")
    referencing = [
        s.camera_id for s in cfg.streams.items if payload.name in s.algorithms
    ]
    override_refs = [
        s.camera_id for s in cfg.streams.items if payload.name in s.algorithm_overrides
    ]
    referencing.extend(x for x in override_refs if x not in referencing)
    if referencing:
        raise HTTPException(
            status_code=400,
            detail=f"algorithm '{payload.name}' referenced by cameras: {', '.join(referencing)}",
        )
    del cfg.algorithms[payload.name]
    save_system_config(cfg)
    return {"name": payload.name}
