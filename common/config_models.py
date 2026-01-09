from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str
    port: int
    public_host: str
    public_http_port: int


class UserBackendConfig(BaseModel):
    base_url: Optional[str] = None
    warning_path: Optional[str] = None
    timeout: Optional[int] = None


class ZLMConfig(BaseModel):
    host: Optional[str] = None
    secret: Optional[str] = None
    vhost: Optional[str] = None
    webrtc_schema: Optional[str] = None
    webrtc_port: Optional[int] = None
    rtmp_base: Optional[str] = None


class InferenceServerConfig(BaseModel):
    base_url: Optional[str] = None
    infer_path: Optional[str] = None
    timeout: Optional[int] = None
    fps: Optional[int] = None


class StreamItem(BaseModel):
    camera_id: str
    rtsp_url: str
    enable_inference: bool = True
    capture_interval: Optional[int] = Field(default=None, alias="capture_interval")
    send_clip: bool = True
    clip_before_seconds: Optional[int] = None
    clip_after_seconds: Optional[int] = None
    algorithms: List[str] = Field(default_factory=list)
    algorithm_overrides: Dict[str, "AlgorithmOverrideConfig"] = Field(
        default_factory=dict
    )


class StreamsConfig(BaseModel):
    default_app: Optional[str] = None
    default_capture_interval: Optional[int] = None
    items: List[StreamItem] = Field(default_factory=list)


class AlgorithmConfig(BaseModel):
    enabled: bool = True
    weight: Optional[str] = None
    device: Optional[str] = None
    conf_threshold: Optional[float] = None
    alert_threshold: Optional[float] = None
    classes: List[str] = Field(default_factory=list)
    roi: Optional[List[Tuple[float, float]]] = None
    color: Optional[Tuple[int, int, int]] = None


class AlgorithmOverrideConfig(BaseModel):
    conf_threshold: Optional[float] = None
    alert_threshold: Optional[float] = None
    classes: Optional[List[str]] = None
    roi: Optional[List[Tuple[float, float]]] = None
    color: Optional[Tuple[int, int, int]] = None


class SystemConfig(BaseModel):
    server: ServerConfig
    user_backend: UserBackendConfig
    zlm: ZLMConfig
    inference_server: InferenceServerConfig
    streams: StreamsConfig
    algorithms: Dict[str, AlgorithmConfig]


StreamItem.update_forward_refs()
