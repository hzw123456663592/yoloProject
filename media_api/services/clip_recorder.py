from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Tuple
from collections import deque
import subprocess

import cv2
import numpy as np


@dataclass
class ClipTask:
    """单次告警对应的一段剪辑任务。"""
    alarm_id: str
    alarm_ts: float
    end_ts: float
    out_path: Path
    before_frames: List[np.ndarray]
    after_frames: List[np.ndarray]


class ClipRecorder:
    """环形缓冲 + 支持多告警并发的剪辑器（方案 B）。

    设计目标：
    - 每一次告警（alarm_id）都会生成一段独立的 mp4；
    - 同一摄像头在同一时间可以有多个剪辑任务并行进行；
    - 上层通过 on_frame() 拿到「已完成剪辑」列表，每个元素是 (alarm_id, tmp_path)。
    """

    def __init__(
        self,
        clips_dir: Path,
        fps: int,
        before_seconds: int,
        after_seconds: int,
        resize_width: int,
        ffmpeg_path: str = "ffmpeg",
    ):
        # clips_dir: 每路摄像头自己的临时 clips 目录（StreamWorker 里传进来的已经是 .../_tmp/<camera_id>）
        self.clips_dir = clips_dir
        self.fps = fps
        self.before_seconds = before_seconds
        self.after_seconds = after_seconds
        self.resize_width = resize_width
        self.ffmpeg_path = ffmpeg_path

        # 环形缓冲：保存最近 before_seconds 秒的帧
        self._history: Deque[Tuple[float, np.ndarray]] = deque()
        # 当前所有还在进行中的剪辑任务
        self._tasks: List[ClipTask] = []

        self.clips_dir.mkdir(parents=True, exist_ok=True)

    # ----------------- 对上层暴露的接口 -----------------

    def start_clip(self, alarm_id: str, alarm_ts: float) -> None:
        """新建一个剪辑任务。

        - alarm_ts: 告警对应的时间戳（StreamWorker 里传进来的 now）
        - 会从当前 history 中拷贝「alarm_ts 之前」的帧作为 before 部分。
        """
        # 已经存在同名任务就不重复创建（防御性处理）
        for t in self._tasks:
            if t.alarm_id == alarm_id:
                return

        # 收集 alarm_ts 之前的帧（history 里本身就只保留了最近 before_seconds 秒）
        before_frames: List[np.ndarray] = [
            f.copy() for ts, f in self._history if ts <= alarm_ts
        ]

        # 临时 mp4 的输出路径（后面由 ClipStore 再移动到正式 clips 目录）
        out_path = self.clips_dir / f"{alarm_id}.mp4"

        task = ClipTask(
            alarm_id=alarm_id,
            alarm_ts=alarm_ts,
            end_ts=alarm_ts + float(self.after_seconds),
            out_path=out_path,
            before_frames=before_frames,
            after_frames=[],
        )
        self._tasks.append(task)

    def on_frame(self, ts: float, frame: np.ndarray) -> List[Tuple[str, Path]]:
        """每来一帧调用一次。

        返回值：[(alarm_id, tmp_path), ...]，表示哪些告警的剪辑已经完成。
        """
        # 1. 环形缓冲：只保留最近 before_seconds 秒
        self._history.append((ts, frame.copy()))
        cutoff = ts - float(self.before_seconds)
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        finished: List[Tuple[str, Path]] = []

        if not self._tasks:
            return finished

        # 2. 把当前帧追加到所有「仍在 after 窗口内」的任务里
        for task in self._tasks:
            if task.alarm_ts < ts <= task.end_ts:
                task.after_frames.append(frame.copy())

        # 3. 找出已经结束窗口的任务，进行 flush
        still_pending: List[ClipTask] = []
        for task in self._tasks:
            if ts > task.end_ts:
                out = self._flush(task)
                if out is not None:
                    finished.append((task.alarm_id, out))
            else:
                still_pending.append(task)

        self._tasks = still_pending
        return finished

    def flush_all(self) -> List[Tuple[str, Path]]:
        """可选：在流结束/进程退出前，把所有未完成任务尽量写盘。

        注意：如果 after 部分时间还没凑够，会根据已有帧写一小段视频。
        """
        finished: List[Tuple[str, Path]] = []
        for task in self._tasks:
            out = self._flush(task)
            if out is not None:
                finished.append((task.alarm_id, out))
        self._tasks.clear()
        return finished

    # ----------------- 内部工具方法 -----------------

    def _flush(self, task: ClipTask) -> Path | None:
        """把某个任务的 before+after 帧写成 mp4 并返回临时文件路径。"""
        frames = task.before_frames + task.after_frames
        if not frames:
            return None

        h, w, _ = frames[0].shape

        # 按需要缩放到统一宽度
        if self.resize_width and self.resize_width > 0 and w != self.resize_width:
            new_w = int(self.resize_width)
            new_h = int(h * new_w / w)
            resized: List[np.ndarray] = []
            for f in frames:
                resized.append(cv2.resize(f, (new_w, new_h)))
            frames = resized
            h, w = new_h, new_w

        task.out_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(self.fps),
            "-i",
            "-",
            "-an",
            "-vcodec",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            str(task.out_path),
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            bufsize=10**8,
        )
        assert proc.stdin is not None
        for f in frames:
            proc.stdin.write(f.tobytes())
        proc.stdin.close()
        proc.wait()
        return task.out_path
