from __future__ import annotations
from fastapi import FastAPI

from common.settings import load_settings
from media_api.routes.streams import router as streams_router
from media_api.routes.alarms import router as alarms_router
from media_api.routes.inference_cb import router as inference_cb_router
from media_api.routes.config import router as config_router
from media_api.services.state import stream_manager

settings = load_settings()

app = FastAPI(title="Media API Service")

app.include_router(streams_router, prefix="/api")
app.include_router(alarms_router, prefix="/api")
app.include_router(inference_cb_router, prefix="/api")
app.include_router(config_router, prefix="/api/config")


@app.on_event("startup")
def on_startup():
    # 启动所有摄像头 worker
    stream_manager.start_all()


@app.on_event("shutdown")
def on_shutdown():
    stream_manager.stop_all()


@app.get("/health")
def health():
    return {"ok": True}
