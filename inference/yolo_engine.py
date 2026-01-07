# inference/yolo_engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
from ultralytics import YOLO  # 需要安装 ultralytics


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float
    cls: int
    label: str


class YoloEngine:
    """
    对 ultralytics.YOLO 做一层简单封装：
    - 支持设定 conf 阈值
    - 支持 class 过滤
    - 提供 ROI 过滤工具
    """

    def __init__(
        self,
        weights_path: str,
        conf_thres: float = 0.5,
        device: Optional[str] = None,
        classes: Optional[Sequence[int]] = None,
    ):
        self.model = YOLO(weights_path)
        self.conf_thres = conf_thres
        self.classes_filter = set(classes) if classes is not None else None

        if device is not None:
            # "cpu" 或 "cuda:0"
            self.model.to(device)

        # 模型的类别名映射
        # ultralytics YOLO 一般有 .names 属性
        self.names = self.model.names

    def infer(self, frame: np.ndarray) -> List[Detection]:
        """
        输入 BGR 格式的 numpy 图像，输出检测框列表。
        """
        # ultralytics 接受 numpy BGR 直接推
        results = self.model.predict(source=frame, conf=self.conf_thres, verbose=False)[0]
        dets: List[Detection] = []

        boxes = results.boxes
        if boxes is None or len(boxes) == 0:
            return dets

        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls = int(box.cls[0])

            if self.classes_filter is not None and cls not in self.classes_filter:
                continue

            label = self.names.get(cls, str(cls)) if isinstance(self.names, dict) else str(cls)
            dets.append(
                Detection(
                    x1=int(x1),
                    y1=int(y1),
                    x2=int(x2),
                    y2=int(y2),
                    conf=conf,
                    cls=cls,
                    label=label,
                )
            )
        return dets

    @staticmethod
    def filter_roi(dets: List[Detection], roi: Optional[List[Tuple[int, int]]]) -> List[Detection]:
        """
        根据多边形 ROI 过滤检测框（使用框中心点）。
        roi: [(x, y), ...]
        """
        if not roi:
            return dets

        contour = np.array(roi, dtype=np.int32)
        kept: List[Detection] = []

        for d in dets:
            cx = (d.x1 + d.x2) // 2
            cy = (d.y1 + d.y2) // 2
            inside = cv2.pointPolygonTest(contour, (cx, cy), False) >= 0
            if inside:
                kept.append(d)

        return kept
