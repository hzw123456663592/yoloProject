from __future__ import annotations
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json


@dataclass
class AlarmRecord:
    alarm_id: str
    camera_id: str
    rtsp_url: str
    timestamp: int
    msg: str
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class AlarmStore:
    """简单的基于 JSONL 的告警存储。"""

    def __init__(self, alarms_dir: Path, public_base: str):
        self.alarms_dir = alarms_dir
        self.public_base = public_base.rstrip("/")
        self.index_path = self.alarms_dir / "alarms.jsonl"
        self.alarms_dir.mkdir(parents=True, exist_ok=True)

    # ---- id & 路径 ----

    def new_alarm_id(self) -> str:
        now = datetime.now()
        # 例：20260104_153012_382
        return now.strftime("%Y%m%d_%H%M%S_") + f"{int(now.microsecond/1000):03d}"

    def _date_folder(self, alarm_id: str) -> str:
        ymd = alarm_id[:8]
        return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"

    def _snapshot_folder(self, alarm_id: str, ensure: bool = False) -> Path:
        date_folder = self._date_folder(alarm_id)
        folder = self.alarms_dir / date_folder
        if ensure:
            folder.mkdir(parents=True, exist_ok=True)
        return folder

    def snapshot_paths(self, alarm_id: str) -> tuple[Path, str]:
        """返回本地路径 + 对外 URL。"""
        folder = self._snapshot_folder(alarm_id, ensure=True)
        img_path = folder / f"{alarm_id}.jpg"
        img_url = f"{self.public_base}/api/snapshots/{folder.name}/{img_path.name}"
        return img_path, img_url

    def snapshot_file_path(self, alarm_id: str, ensure_dir: bool = False) -> Path:
        folder = self._snapshot_folder(alarm_id, ensure=ensure_dir)
        return folder / f"{alarm_id}.jpg"

    # ---- CRUD ----

    def save_alarm(self, rec: AlarmRecord) -> None:
        line = json.dumps(asdict(rec), ensure_ascii=False)
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _update_field(self, alarm_id: str, field_name: str, value: Any) -> None:
        if not self.index_path.exists():
            return
        rows: List[Dict[str, Any]] = []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("alarm_id") == alarm_id:
                    obj[field_name] = value
                rows.append(obj)
        with self.index_path.open("w", encoding="utf-8") as f:
            for obj in rows:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def update_clip_url(self, alarm_id: str, clip_url: Optional[str]) -> None:
        self._update_field(alarm_id, "clip_url", clip_url)

    def update_snapshot(
        self,
        alarm_id: str,
        snapshot_url: Optional[str],
        snapshot_path: Optional[str],
    ) -> None:
        self._update_field(alarm_id, "snapshot_url", snapshot_url)
        self._update_field(alarm_id, "snapshot_path", snapshot_path)

    def list_alarms(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.index_path.exists():
            return []
        items: List[Dict[str, Any]] = []
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                items.append(json.loads(line))
        # 最近的在前面
        return items[-limit:][::-1]

    def get_alarm(self, alarm_id: str) -> Optional[Dict[str, Any]]:
        if not self.index_path.exists():
            return None
        with self.index_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("alarm_id") == alarm_id:
                    return obj
        return None
