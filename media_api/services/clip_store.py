from __future__ import annotations
from pathlib import Path
import shutil
from typing import Callable, List, Optional


class ClipStore:
    def __init__(
        self,
        clips_dir: Path,
        public_base: str,
        max_clips_per_day: int = 3,
        cleanup_callback: Optional[Callable[[List[str]], None]] = None,
    ):
        self.clips_dir = clips_dir
        self.public_base = public_base.rstrip("/")
        self.max_clips_per_day = max_clips_per_day
        self._cleanup_callback = cleanup_callback

    def _date_folder(self, alarm_id: str) -> str:
        ymd = alarm_id[:8]
        return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"

    def allocate_clip_path(self, alarm_id: str) -> Path:
        date_folder = self._date_folder(alarm_id)
        folder = self.clips_dir / date_folder
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{alarm_id}.mp4"

    def save_generated_clip(self, alarm_id: str, tmp_path: Path) -> str:
        dst = self.allocate_clip_path(alarm_id)
        shutil.move(str(tmp_path), str(dst))
        self._cleanup_old_clips(dst.parent)
        return f"{self.public_base}/api/clips/{self._date_folder(alarm_id)}/{dst.name}"

    def _cleanup_old_clips(self, folder: Path) -> None:
        if self.max_clips_per_day <= 0:
            return

        mp4_files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"],
            key=lambda p: p.stat().st_mtime,
        )
        deleted_alarm_ids: List[str] = []
        while len(mp4_files) > self.max_clips_per_day:
            oldest = mp4_files.pop(0)
            deleted_alarm_ids.append(oldest.stem)
            try:
                oldest.unlink()
            except Exception as exc:
                print(f"[ClipStore] failed to delete old clip {oldest}: {exc}")

        if deleted_alarm_ids and self._cleanup_callback:
            try:
                self._cleanup_callback(deleted_alarm_ids)
            except Exception as exc:
                print(f"[ClipStore] cleanup callback failed: {exc}")
