# inference/api.py
from __future__ import annotations
from fastapi import FastAPI, HTTPException

from common.settings import load_settings
from common.schemas import InferenceRequest, InferenceResponse
from .service import InferenceService

settings = load_settings()
app = FastAPI(title="Inference Service")

_service = InferenceService()


@app.post("/infer", response_model=InferenceResponse)
def infer(req: InferenceRequest):
    if not req.algorithms:
        raise HTTPException(status_code=400, detail="algorithms is empty")
    return _service.infer(req)


@app.get("/health")
def health():
    return {"ok": True}
