from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import os
import yaml


@dataclass(frozen=True)
class Settings:
    raw: Dict[str, Any]
    project_root: Path
    config_path: Path

    @property
    def server(self) -> Dict[str, Any]:
        return self.raw.get("server", {})

    @property
    def zlm(self) -> Dict[str, Any]:
        return self.raw.get("zlm", {})

    @property
    def storage(self) -> Dict[str, Any]:
        return self.raw.get("storage", {})

    @property
    def streams(self) -> Dict[str, Any]:
        return self.raw.get("streams", {})

    @property
    def alarm(self) -> Dict[str, Any]:
        return self.raw.get("alarm", {})

    @property
    def inference_server(self) -> Dict[str, Any]:
        # 推理服务的 HTTP 地址（后面实现推理端时会用）
        return self.raw.get("inference_server", {})

    @property
    def webhooks(self) -> Dict[str, Any]:
        return self.raw.get("webhooks", {})

    @property
    def algorithms(self) -> Dict[str, Any]:
        # ★★ 关键：推理端需要用到的算法配置就在这里取 ★★
        return self.raw.get("algorithms", {})

    @property
    def user_backend(self) -> Dict[str, Any]:
        return self.raw.get("user_backend", {})



def _detect_project_root() -> Path:
    # common/settings.py -> common -> project root
    return Path(__file__).resolve().parents[1]


def load_settings(config_path: str | os.PathLike | None = None) -> Settings:
    """加载 YAML 配置并创建数据目录。"""
    project_root = _detect_project_root()

    if config_path is None:
        env_cfg = os.getenv("APP_CONFIG")
        if env_cfg:
            config_path = env_cfg
        else:
            # 默认使用 <project_root>/configs/config.yaml（跟你现在项目一致）
            config_path = project_root / "configs" / "config.yaml"

    p = Path(config_path).expanduser()
    if not p.is_absolute():
        p = (project_root / p).resolve()

    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    storage = raw.setdefault("storage", {})
    storage.setdefault("data_dir", str(project_root / "data"))
    storage.setdefault("alarms_dir", str(project_root / "data" / "alarms"))
    storage.setdefault("clips_dir", str(project_root / "data" / "clips"))

    for k in ("data_dir", "alarms_dir", "clips_dir"):
        Path(storage[k]).mkdir(parents=True, exist_ok=True)

    return Settings(raw=raw, project_root=project_root, config_path=p)
