
from __future__ import annotations
from dataclasses import dataclass
import base64
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

from common.config_models import (
    AlgorithmConfig,
    AlgorithmOverrideConfig,
    SystemConfig,
)
from common.config_store import load_system_config
from common.settings import load_settings
from common.schemas import (
    InferenceRequest,
    InferenceResponse,
    InferenceResultItem,
    DetectedObject,
    InferenceCallback,
)
from .yolo_engine import YoloEngine, Detection


@dataclass
class RoiConfig:
    coord_type: str  # "relative" 或 "absolute"
    points: List[Tuple[float, float]]


def _point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    射线法判断点是否在多边形内部。
    polygon: [(x1,y1), (x2,y2), ...]
    """
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        # 判断线段是否跨越水平射线
        intersect = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1
        )
        if intersect:
            inside = not inside
        x1, y1 = x2, y2
    return inside


class InferenceService:
    """
    推理服务核心：
    - 解析配置里的 algorithms（B/H/Z）
    - 维护多个 YoloEngine 实例
    - 对每张图片计算 Y 数组，与 Z 阈值对比
    - 若有触发，调用流媒体端回调 M
    - 支持从 camera_roi.json 读取电子围栏（ROI），按 camera_id + algorithm 过滤检测框
    """

    def __init__(self):
        self.settings = load_settings()
        self.system_config: SystemConfig = load_system_config()
        self.alg_cfg: Dict[str, AlgorithmConfig] = self.system_config.algorithms or {}
        self.stream_overrides: Dict[str, Dict[str, AlgorithmOverrideConfig]] = {}
        for stream in self.system_config.streams.items:
            if stream.algorithm_overrides:
                self.stream_overrides[stream.camera_id] = stream.algorithm_overrides

        # 算法对应的固定颜色表
        self._algo_colors: Dict[str, Tuple[int, int, int]] = {}
        self._load_algorithm_colors()

        # 加载 YOLO 模型（一个算法对应一个模型实例）
        self.models: Dict[str, YoloEngine] = {}
        for name, cfg in self.alg_cfg.items():
            enabled = cfg.enabled
            if not enabled:
                print(f"[InferenceService] algorithm '{name}' is disabled in config, skip loading.")
                continue

            weight = cfg.weight
            device = cfg.device
            conf_threshold = float(cfg.conf_threshold or 0.5)

            classes_cfg = cfg.classes
            classes_ids: Optional[List[int]] = None
            if isinstance(classes_cfg, list):
                tmp: List[int] = []
                for c in classes_cfg:
                    try:
                        tmp.append(int(c))
                    except Exception:
                        pass
                if tmp:
                    classes_ids = tmp

            try:
                model = YoloEngine(
                    weights_path=weight,
                    conf_thres=conf_threshold,
                    device=device,
                    classes=classes_ids,
                )
            except Exception as e:
                print(f"[InferenceService] failed to load model for '{name}': {e}")
                continue

            self.models[name] = model
            print(f"[InferenceService] algorithm '{name}' loaded, weight={weight}, device={device}")

        # 回调到流媒体端的 URL
        self.callback_url: Optional[str] = self.settings.webhooks.get("inference_callback")

        # 电子围栏 JSON 文件路径：<storage.data_dir>/camera_roi.json
        storage = getattr(self.settings, "storage", {}) or {}
        data_dir = storage.get("data_dir", "./data")
        self._roi_file = Path(data_dir) / "camera_roi.json"
        self._roi_map: Dict[str, Dict[str, RoiConfig]] = self._load_roi_map()

    # ---------------- 算法颜色 ----------------

    _DEFAULT_COLOR_PALETTE: List[Tuple[int, int, int]] = [
        (0, 255, 255),
        (0, 165, 255),
        (0, 255, 0),
        (255, 0, 0),
        (255, 255, 0),
        (255, 0, 255),
        (128, 0, 128),
    ]

    def _load_algorithm_colors(self) -> None:
        palette = self._DEFAULT_COLOR_PALETTE
        for idx, (name, cfg) in enumerate(self.alg_cfg.items()):
            color_cfg = cfg.color
            if (
                isinstance(color_cfg, list)
                and len(color_cfg) >= 3
                and all(isinstance(v, (int, float)) for v in color_cfg[:3])
            ):
                r, g, b = map(int, color_cfg[:3])
                self._algo_colors[name] = (b, g, r)
            else:
                self._algo_colors[name] = palette[idx % len(palette)]

    def _get_effective_algo_config(
        self, camera_id: str, algorithm: str
    ) -> Optional[AlgorithmConfig]:
        base = self.alg_cfg.get(algorithm)
        if base is None:
            return None
        overrides = self.stream_overrides.get(camera_id, {})
        override = overrides.get(algorithm)
        if not override:
            return base
        merged = base.dict()
        merged.update(override.dict(exclude_none=True))
        return AlgorithmConfig(**merged)


    # ---------------- ROI 相关 ----------------

    def _load_roi_map(self) -> Dict[str, Dict[str, RoiConfig]]:
        """
        从 JSON 文件读取全部 ROI 配置。
        格式示例：
        {
          "camera_001": {
            "玩手机": {
              "coord_type": "relative",
              "points": [[0.1,0.2],[0.3,0.2],...]
            }
          },
          "camera_002": {
            "玩手机": {
              "coord_type": "relative",
              "points": [...]
            }
          }
        }
        """
        if not self._roi_file.exists():
            return {}

        try:
            with self._roi_file.open("r", encoding="utf-8") as f:
                raw = json.load(f) or {}
        except Exception as e:
            print(f"[InferenceService] load roi file failed: {e}")
            return {}

        roi_map: Dict[str, Dict[str, RoiConfig]] = {}
        for cam_id, alg_dict in raw.items():
            if not isinstance(alg_dict, dict):
                continue
            roi_map[cam_id] = {}
            for alg_name, cfg in alg_dict.items():
                if not isinstance(cfg, dict):
                    continue
                coord_type = cfg.get("coord_type", "relative")
                points = cfg.get("points") or []
                try:
                    pts: List[Tuple[float, float]] = [
                        (float(x), float(y)) for x, y in points
                    ]
                except Exception:
                    pts = []
                roi_map[cam_id][alg_name] = RoiConfig(coord_type=coord_type, points=pts)
        return roi_map

    def _get_roi(self, camera_id: str, algorithm: str) -> Optional[RoiConfig]:
        cam_dict = self._roi_map.get(camera_id)
        if not cam_dict:
            return None
        return cam_dict.get(algorithm)

    def _apply_roi_filter(
        self,
        dets: List[Detection],
        frame_shape,
        camera_id: str,
        algorithm: str,
    ) -> List[Detection]:
        """
        根据 camera_id + algorithm 对检测结果做电子围栏过滤：
        - 若无 ROI 配置，则原样返回
        - 若有 ROI：
          - coord_type == "relative" → points 为 [0~1] 归一化，需乘以 w,h
          - coord_type == "absolute" → points 为像素坐标，直接用
        """
        roi_cfg = self._get_roi(camera_id, algorithm)
        if not roi_cfg or not roi_cfg.points:
            return dets

        h, w = frame_shape[:2]

        if roi_cfg.coord_type == "relative":
            polygon = [(x * w, y * h) for x, y in roi_cfg.points]
        else:  # "absolute"
            polygon = roi_cfg.points

        kept: List[Detection] = []
        for det in dets:
            cx = 0.5 * (det.x1 + det.x2)
            cy = 0.5 * (det.y1 + det.y2)
            if _point_in_polygon(cx, cy, polygon):
                kept.append(det)
        return kept

    # ---- 工具方法 ----

    @staticmethod
    def _decode_image(b64: str) -> np.ndarray:
        """
        base64 -> BGR numpy
        """
        raw = base64.b64decode(b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("decode image failed")
        return img

    @staticmethod
    def _encode_image(frame: np.ndarray) -> str:
        """
        BGR numpy -> base64(jpg)
        """
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("encode image failed")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def _color_from_algorithm(self, name: str) -> Tuple[int, int, int]:
        """返回算法对应的 BGR 颜色，先查配置、再回退到默认色卡。"""
        if name in self._algo_colors:
            return self._algo_colors[name]
        palette = self._DEFAULT_COLOR_PALETTE
        return palette[abs(hash(name)) % len(palette)]

    _FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}
    _FONT_PATH_CANDIDATES = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]

    @classmethod
    def _get_font(cls, size: int) -> ImageFont.FreeTypeFont:
        """按大小缓存字体，优先使用支持中文的系统字体。"""
        if size in cls._FONT_CACHE:
            return cls._FONT_CACHE[size]
        for path in cls._FONT_PATH_CANDIDATES:
            if path.exists():
                try:
                    font = ImageFont.truetype(str(path), size)
                    cls._FONT_CACHE[size] = font
                    return font
                except Exception:
                    continue
        font = ImageFont.load_default()
        cls._FONT_CACHE[size] = font
        return font

    def _draw_result_annotations(self, frame: np.ndarray, results: List[InferenceResultItem]) -> np.ndarray:
        """在帧上画出所有算法检测到的 bbox（包含算法名 + 置信度），支持中文。"""
        annotated = frame.copy()
        image_pil = Image.fromarray(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image_pil)
        font = self._get_font(18)

        for result in results:
            color_bgr = self._color_from_algorithm(result.algorithm)
            color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
            for obj in result.objects:
                if len(obj.bbox) != 4:
                    continue
                x1, y1, x2, y2 = map(int, obj.bbox)
                draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=2)
                label = f"{result.algorithm}:{obj.conf:.2f}"
                box_width = max(1, x2 - x1 - 4)
                font_size = 18
                font = self._get_font(font_size)
                bbox = font.getbbox(label)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                while text_w > box_width and font_size > 10:
                    font_size -= 1
                    font = self._get_font(font_size)
                    bbox = font.getbbox(label)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                text_origin = (x1, y1 - text_h - 4 if y1 - text_h - 4 > 0 else y1 + 4)
                draw.text(
                    (text_origin[0], text_origin[1]),
                    label,
                    fill=color_rgb,
                    font=font,
                )

        return cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

    # ---- 单算法推理 ----

    def _run_one_algorithm(
        self,
        alg_name: str,
        cfg: AlgorithmConfig,
        model: YoloEngine,
        frame: np.ndarray,
        camera_id: str,
    ) -> InferenceResultItem:
        """
        对单个算法 Bi 跑推理并得到这个算法对应的 Y[i]。
        这里已经集成电子围栏逻辑：
          1. 先 YOLO 推理
          2. 再根据 camera_id + alg_name 应用 ROI 过滤
        """
        # 1) YOLO 推理得到所有检测框
        dets: List[Detection] = model.infer(frame)

        # 2) 电子围栏过滤（优先使用 camera_roi.json 里的配置）
        dets = self._apply_roi_filter(
            dets=dets,
            frame_shape=frame.shape,
            camera_id=camera_id,
            algorithm=alg_name,
        )

        # 3) 根据业务场景计算一个 score：
        #    这里简单做法：所有 dets 中最大的 conf 作为 Y[i]
        score = max((d.conf for d in dets), default=0.0)

        threshold = float(cfg.alert_threshold or 0.5)
        triggered = score >= threshold

        # 4) 把目标列表也一并返回，方便前端调试或后续扩展
        objects = [
            DetectedObject(
                cls=d.label,
                cls_id=d.cls,
                conf=float(d.conf),
                bbox=[d.x1, d.y1, d.x2, d.y2],
            )
            for d in dets
        ]

        return InferenceResultItem(
            algorithm=alg_name,
            score=float(score),
            threshold=threshold,
            triggered=triggered,
            objects=objects,
        )

    # ---- 对外主接口 ----

    def infer(self, req: InferenceRequest) -> InferenceResponse:
        """
        单张图片推理：
        - 支持多个算法
        - 返回结果列表
        - 若有触发则调用回调 M
        """
        frame = self._decode_image(req.image_base64)

        results: List[InferenceResultItem] = []
        any_triggered = False

        for alg_name in req.algorithms:
            model = self.models.get(alg_name)
            if model is None:
                continue
            effective_cfg = self._get_effective_algo_config(req.camera_id, alg_name)
            if effective_cfg is None:
                continue

            result = self._run_one_algorithm(
                alg_name=alg_name,
                cfg=effective_cfg,
                model=model,
                frame=frame,
                camera_id=req.camera_id,
            )
            results.append(result)
            if result.triggered:
                any_triggered = True

        resp = InferenceResponse(
            camera_id=req.camera_id,
            timestamp=req.timestamp,
            results=results,
            any_triggered=any_triggered,
        )

        # 调试打印（如果你之前已经加了，可以保留）
        print(f"[Inference] camera={req.camera_id}, any_triggered={any_triggered}")
        for r in results:
            print(
                f"  alg={r.algorithm}, "
                f"score={r.score:.3f}, thr={r.threshold:.3f}, "
                f"triggered={r.triggered}"
            )

        annotated_frame = self._draw_result_annotations(frame, results)

        # 如果有任何算法触发告警，调用流媒体端回调接口 M
        if any_triggered and self.callback_url:
            try:
                img_b64 = self._encode_image(annotated_frame)
                cb = InferenceCallback(
                    camera_id=req.camera_id,
                    timestamp=req.timestamp,
                    results=results,
                    image_base64=img_b64,
                )
                requests.post(
                    self.callback_url,
                    json=cb.dict(),
                    timeout=5,
                )
            except Exception as e:
                print("[InferenceService] callback failed:", e)

        return resp




