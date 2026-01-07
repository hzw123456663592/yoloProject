from __future__ import annotations
from fastapi import APIRouter, HTTPException

from common.schemas import InferenceCallback
from media_api.services.state import stream_manager

router = APIRouter()


@router.post("/inference/callback")
def inference_callback(cb: InferenceCallback):
    """
    推理端通过 M 调用这里：

    1. 根据 results 组织一个简单的告警描述 msg
    2. 找到对应的 StreamWorker
    3. 生成 alarm_id，调用 worker.notify_alarm，启动剪辑任务
    """
    if not cb.results:
        raise HTTPException(status_code=400, detail="empty results")

    triggered_parts = [
        f"{r.algorithm}@{r.score:.2f}/{r.threshold:.2f}"
        for r in cb.results
        if r.triggered
    ]
    if triggered_parts:
        msg = "; ".join(triggered_parts)
    else:
        msg = "; ".join(f"{r.algorithm}@{r.score:.2f}" for r in cb.results)

    worker = stream_manager.get_worker(cb.camera_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"worker for camera {cb.camera_id} not found")

    alarm_id = stream_manager.alarm_store.new_alarm_id()
    worker.notify_alarm(alarm_id=alarm_id, alarm_ts=cb.timestamp, msg=msg,image_base64=cb.image_base64,)

    return {"alarm_id": alarm_id}
