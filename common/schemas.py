from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# ---------- 流管理（流媒体端） ----------

class StreamStartRequest(BaseModel):
    rtsp_url: str
    camera_id: Optional[str] = None


class StreamStartResponse(BaseModel):
    app: str
    stream: str
    webrtc_url: str
    rtsp_url: str
    camera_id: str


# ---------- 告警（对前端暴露） ----------

class AlarmItem(BaseModel):
    alarm_id: str
    camera_id: str
    rtsp_url: str
    timestamp: int
    msg: str
    snapshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class AlarmListResponse(BaseModel):
    items: List[AlarmItem]


# ---------- 推理相关 ----------

class DetectedObject(BaseModel):
    cls: str
    cls_id: int
    conf: float
    bbox: List[int]  # [x1, y1, x2, y2]


class InferenceResultItem(BaseModel):
    algorithm: str
    score: float
    threshold: float
    triggered: bool
    objects: List[DetectedObject] = Field(default_factory=list)


class InferenceCallback(BaseModel):
    """
    推理端 -> 流媒体端 回调 M 使用的结构
    """
    camera_id: str
    timestamp: float
    results: List[InferenceResultItem]
    image_base64: Optional[str] = None

class InferenceRequest(BaseModel):
    """
    流媒体端 -> 推理端 的请求结构
    """
    camera_id: str
    algorithms: List[str]
    image_base64: str  # JPEG/PNG 的 base64
    timestamp: float


class InferenceResponse(BaseModel):
    camera_id: str
    timestamp: float
    results: List[InferenceResultItem]
    any_triggered: bool
