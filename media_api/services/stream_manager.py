from __future__ import annotations
from threading import Event
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.settings import load_settings
from media_api.services.clip_store import ClipStore
from media_api.services.alarm_store import AlarmStore
from media_api.services.stream_worker import StreamWorker
from media_api.services.user_backend_client import UserBackendClient


class StreamManager:
    """根据 config.yaml 启动 / 管理所有摄像头 worker。"""

    def __init__(self):
        self.settings = load_settings()
        self.stop_event = Event()

        storage = self.settings.storage
        public_base = f"http://{self.settings.server['public_host']}:{self.settings.server['public_http_port']}"

        self.alarm_store = AlarmStore(Path(storage["alarms_dir"]), public_base)

        clip_limit = int(self.settings.alarm.get("clip_daily_limit", 3) or 3)
        self.clip_store = ClipStore(
            Path(storage["clips_dir"]),
            public_base,
            max_clips_per_day=clip_limit,
            cleanup_callback=self._cleanup_clip_resources,
        )

        backend_cfg = self.settings.user_backend
        self.user_backend_client: Optional[UserBackendClient] = None
        if backend_cfg.get("base_url"):
            self.user_backend_client = UserBackendClient(
                base_url=backend_cfg["base_url"],
                warning_path=backend_cfg.get("warning_path", "/addVideo/warning"),
                timeout=int(backend_cfg.get("timeout", 10)),
            )

        self.workers: Dict[str, StreamWorker] = {}

    def start_all(self) -> None:
        items: List[dict] = self.settings.streams.get("items", [])
        default_interval = int(self.settings.streams.get("default_capture_interval", 3) or 3)

        for item in items:
            cam_id = item["camera_id"]
            rtsp = item["rtsp_url"]
            enable_infer = bool(item.get("enable_inference", True))
            if not enable_infer:
                continue
            if cam_id in self.workers:
                continue

            capture_interval = int(item.get("capture_interval", default_interval))
            send_clip = bool(item.get("send_clip", True))
            before_s = int(item.get("clip_before_seconds", self.settings.alarm.get("clip_before_seconds", 10)))
            after_s = int(item.get("clip_after_seconds", self.settings.alarm.get("clip_after_seconds", 10)))
            algorithms = item.get("algorithms", [])

            worker = StreamWorker(
                camera_id=cam_id,
                rtsp_url=rtsp,
                algorithms=algorithms,
                capture_interval=capture_interval,
                send_clip=send_clip,
                clip_before_seconds=before_s,
                clip_after_seconds=after_s,
                clip_store=self.clip_store,
                alarm_store=self.alarm_store,
                stop_event=self.stop_event,
                alarm_reporter=self.user_backend_client
            )
            worker.start()
            self.workers[cam_id] = worker
            print(f"[StreamManager] started worker for {cam_id}")

    def stop_all(self) -> None:
        self.stop_event.set()
        for w in self.workers.values():
            w.join(timeout=2.0)

    def get_worker(self, camera_id: str) -> StreamWorker | None:
        return self.workers.get(camera_id)

    def _cleanup_clip_resources(self, alarm_ids: List[str]) -> None:
        for alarm_id in alarm_ids:
            self._remove_media_metadata(alarm_id)

    def _remove_media_metadata(self, alarm_id: str) -> None:
        snapshot_path = self.alarm_store.snapshot_file_path(alarm_id)
        if snapshot_path.exists():
            try:
                snapshot_path.unlink()
            except Exception as exc:
                print(f"[StreamManager] failed to remove snapshot for {alarm_id}: {exc}")
        self.alarm_store.update_snapshot(alarm_id, None, None)
        self.alarm_store.update_clip_url(alarm_id, None)
