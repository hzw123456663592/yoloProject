from __future__ import annotations
from media_api.services.stream_manager import StreamManager

# 全局唯一的 StreamManager 实例，供 main 和各个路由使用
stream_manager = StreamManager()
