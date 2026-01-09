from __future__ import annotations
from pathlib import Path
import shutil
from typing import Callable, List, Optional, Tuple


class ClipStore:
    def __init__(
        self,
        clips_dir: Path,
        public_base: str,
        max_clips_per_camera: int = 3,
        cleanup_callback: Optional[Callable[[List[Tuple[str, str]]], None]] = None,
    ):
        self.clips_dir = clips_dir
        self.public_base = public_base.rstrip("/")
        self.max_clips_per_camera = max_clips_per_camera
        self._cleanup_callback = cleanup_callback

    def _date_folder(self, alarm_id: str) -> str:
        ymd = alarm_id[:8]
        return f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"

    def allocate_clip_path(self, alarm_id: str, camera_id: str) -> Path:
        date_folder = self._date_folder(alarm_id)
        folder = self.clips_dir / date_folder / camera_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{alarm_id}.mp4"

    def _camera_folder(self, alarm_id: str, camera_id: str) -> Path:
        return self.clips_dir / self._date_folder(alarm_id) / camera_id

    def save_generated_clip(self, alarm_id: str, tmp_path: Path, camera_id: str) -> str:
        dst = self.allocate_clip_path(alarm_id, camera_id)
        shutil.move(str(tmp_path), str(dst))
        self._cleanup_old_clips(dst.parent)
        return f"{self.public_base}/api/clips/{self._date_folder(alarm_id)}/{camera_id}/{dst.name}"

    def _cleanup_old_clips(self, folder: Path) -> None:
        if self.max_clips_per_camera <= 0:
            return

        mp4_files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"],
            key=lambda p: p.stat().st_mtime,
        )
        deleted: List[Tuple[str, str]] = []
        camera_id = folder.name
        while len(mp4_files) > self.max_clips_per_camera:
            oldest = mp4_files.pop(0)
            deleted.append((oldest.stem, camera_id))
            try:
                oldest.unlink()
            except Exception as exc:
                print(f"[ClipStore] failed to delete old clip {oldest}: {exc}")

        if deleted and self._cleanup_callback:
            try:
                self._cleanup_callback(deleted)
            except Exception as exc:
                print(f"[ClipStore] cleanup callback failed: {exc}")
