from __future__ import annotations
from threading import Thread, Event
from typing import List, Optional
from pathlib import Path

import time
import cv2
import numpy as np
import requests
import base64

from common.settings import load_settings
from media_api.services.rtsp_reader import RTSPFrameReader
from media_api.services.clip_recorder import ClipRecorder
from media_api.services.clip_store import ClipStore
from media_api.services.alarm_store import AlarmStore, AlarmRecord
from media_api.services.user_backend_client import UserBackendClient


class StreamWorker(Thread):
    """一条摄像头流：拉 RTSP + 抽帧发推理 + 维护环形缓冲并生成 clip。"""

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        algorithms: List[str],
        capture_interval: int,
        send_clip: bool,
        clip_before_seconds: int,
        clip_after_seconds: int,
        clip_store: ClipStore,
        alarm_store: AlarmStore,
        stop_event: Event,
        alarm_reporter: Optional[UserBackendClient] = None,
    ):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.algorithms = algorithms
        self.capture_interval = capture_interval
        self.send_clip = send_clip
        self.clip_before_seconds = clip_before_seconds
        self.clip_after_seconds = clip_after_seconds
        self.clip_store = clip_store
        self.alarm_store = alarm_store
        self.stop_event = stop_event

        self.settings = load_settings()
        self.reader = RTSPFrameReader(rtsp_url)
        self.alarm_reporter = alarm_reporter

        storage = self.settings.storage
        # 每路摄像头自己的临时 clips 目录：.../clips/_tmp/<camera_id>
        tmp_clips_dir = Path(storage["clips_dir"]) / "_tmp" / camera_id

        fps = int(self.settings.inference_server.get("fps", 10) or 10)
        resize_width = int(self.settings.alarm.get("clip_resize_width", 640) or 640)
        ffmpeg_path = self.settings.alarm.get("ffmpeg_path", "ffmpeg")

        self.clip_recorder = ClipRecorder(
            clips_dir=tmp_clips_dir,
            fps=fps,
            before_seconds=self.clip_before_seconds,
            after_seconds=self.clip_after_seconds,
            resize_width=resize_width,
            ffmpeg_path=ffmpeg_path,
        )

        self._last_capture_ts = 0.0

        # 推理服务 HTTP 设置
        inf_cfg = self.settings.inference_server
        base_url = inf_cfg.get("base_url")
        path = inf_cfg.get("infer_path", "/infer")
        self._infer_url: Optional[str] = None
        if base_url:
            self._infer_url = base_url.rstrip("/") + path
        self._infer_timeout = int(inf_cfg.get("timeout", 5) or 5)

    # ---- 提供给回调路由调用 ----

    def notify_alarm(
        self,
        alarm_id: str,
        alarm_ts: float,
        msg: str,
        image_base64: Optional[str] = None,
    ) -> None:
        """推理端回调后，由路由调用：记录告警并启动剪辑任务。"""
        snapshot_path: Optional[str] = None
        snapshot_url: Optional[str] = None

        # 如果有图片就先落地成 jpg
        if image_base64:
            try:
                from base64 import b64decode

                data = b64decode(image_base64)
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    # 根据 alarm_id 生成图片路径 / url
                    img_path, img_url = self.alarm_store.snapshot_paths(
                        alarm_id, self.camera_id
                    )
                    img_path.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(img_path), img)
                    snapshot_path = str(img_path)
                    snapshot_url = img_url
            except Exception as e:
                print(f"[StreamWorker {self.camera_id}] save snapshot failed: {e}")

            # 触发剪辑任务（在保存完图之后）
            self.alarm_store.cleanup_old_snapshots(self.camera_id, alarm_id)

        if self.send_clip:
            # 方案 B：每一次告警都单独创建一个剪辑任务
            self.clip_recorder.start_clip(alarm_id, alarm_ts)

        # 创建告警记录
        rec = AlarmRecord(
            alarm_id=alarm_id,
            camera_id=self.camera_id,
            rtsp_url=self.rtsp_url,
            timestamp=int(alarm_ts),
            msg=msg,
            snapshot_path=snapshot_path,
            snapshot_url=snapshot_url,
        )
        self.alarm_store.save_alarm(rec)

    # ---- 主循环 ----

    @staticmethod
    def _encode_b64(frame: np.ndarray) -> str:
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("encode jpg failed")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def _handle_finished_clip(self, alarm_id: str, clip_tmp_path: Path) -> None:
        """把临时 mp4 落盘、更新索引并推给用户后端。"""
        # 1. 先把临时 mp4 移到正式路径
        clip_url = self.clip_store.save_generated_clip(alarm_id, clip_tmp_path, self.camera_id)
        self.alarm_store.update_clip_url(alarm_id, clip_url)

        # 2. 算出「正式 mp4 的本地路径」
        final_video_path = self.clip_store.allocate_clip_path(alarm_id, self.camera_id)

        # 3. 给用户后端发 base64 + 文件流
        if self.alarm_reporter is not None:
            alarm = self.alarm_store.get_alarm(alarm_id)
            if alarm is None:
                print(
                    f"[StreamWorker {self.camera_id}] alarm {alarm_id} not found in store"
                )
            else:
                snapshot_path = alarm.get("snapshot_path")
                if not snapshot_path:
                    print(
                        f"[StreamWorker {self.camera_id}] alarm {alarm_id} has no snapshot, skip backend"
                    )
                else:
                    try:
                        self.alarm_reporter.send_alarm(
                            image_path=Path(snapshot_path),
                            video_path=final_video_path,
                            sensor_id=alarm["camera_id"],
                            msg=alarm["msg"],
                            ts=alarm["timestamp"],
                        )
                    except Exception as e:
                        print(
                            f"[StreamWorker {self.camera_id}] send to user backend failed: {e}"
                        )

    def run(self) -> None:
        for frame in self.reader.frames():
            if self.stop_event.is_set():
                break

            now = time.time()

            # 1. 所有帧都放入环形缓冲，并让剪辑器处理多任务
            finished_clips = self.clip_recorder.on_frame(now, frame)

            # 对已经完成的所有剪辑任务，逐个落盘并上报
            for alarm_id, clip_tmp_path in finished_clips:
                self._handle_finished_clip(alarm_id, clip_tmp_path)

            # 2. 按间隔抽帧，发给推理服务
            if (
                self.capture_interval > 0
                and self._infer_url is not None
                and self.algorithms
                and now - self._last_capture_ts >= self.capture_interval
            ):
                self._last_capture_ts = now
                try:
                    img_b64 = self._encode_b64(frame)
                    payload = {
                        "camera_id": self.camera_id,
                        "algorithms": self.algorithms,
                        "image_base64": img_b64,
                        "timestamp": now,
                    }
                    requests.post(
                        self._infer_url, json=payload, timeout=self._infer_timeout
                    )
                except Exception as e:
                    print(
                        f"[StreamWorker {self.camera_id}] infer request failed:", e
                    )

        # 循环结束（例如 stop_event 被设置或 RTSP 断开）后，把剩余未完成的任务尽量写盘
        for alarm_id, clip_tmp_path in self.clip_recorder.flush_all():
            self._handle_finished_clip(alarm_id, clip_tmp_path)

        self.reader.close()
