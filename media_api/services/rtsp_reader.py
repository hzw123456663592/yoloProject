from __future__ import annotations
import time
from typing import Iterator, Optional

import av

try:
    from av.error import AVError  # type: ignore
except Exception:  # av 版本不同时兜底
    AVError = Exception  # type: ignore


class RTSPFrameReader:
    """简单的 RTSP 拉流封装，按帧返回 numpy 数组。"""

    def __init__(self, rtsp_url: str, reconnect_interval: float = 3.0):
        self.url = rtsp_url
        self.reconnect_interval = reconnect_interval
        self._container: Optional[av.container.input.InputContainer] = None
        self._closed = False

    def close(self) -> None:
        self._closed = True
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None

    def frames(self) -> Iterator["np.ndarray"]:
        import numpy as np  # 延迟导入

        while not self._closed:
            try:
                self._container = av.open(self.url, timeout=5.0)
                for frame in self._container.decode(video=0):
                    yield frame.to_ndarray(format="bgr24")
            except AVError:
                # 失败就稍等重连
                pass
            finally:
                if self._container is not None:
                    try:
                        self._container.close()
                    except Exception:
                        pass
                    self._container = None

            if self._closed:
                break
            time.sleep(self.reconnect_interval)
