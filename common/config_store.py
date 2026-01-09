from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

from common.config_models import (
    AlgorithmConfig,
    InferenceServerConfig,
    SystemConfig,
    StreamsConfig,
    UserBackendConfig,
    ServerConfig,
    ZLMConfig,
)
from common.settings import load_settings


def _deep_merge(dest: Dict[str, Any], src: Dict[str, Any]) -> None:
    for key, value in src.items():
        if (
            isinstance(value, dict)
            and isinstance(dest.get(key), dict)
            and dest.get(key) is not None
        ):
            _deep_merge(dest[key], value)
        else:
            dest[key] = value


def _build_default_config(settings) -> SystemConfig:
    server = ServerConfig(**(settings.server or {}))
    user_backend = UserBackendConfig(**(settings.user_backend or {}))
    zlm = ZLMConfig(**(settings.zlm or {}))
    inference_server = InferenceServerConfig(**(settings.inference_server or {}))
    streams = StreamsConfig(**(settings.streams or {}))

    algorithms: Dict[str, AlgorithmConfig] = {}
    for name, cfg in (settings.algorithms or {}).items():
        algorithms[name] = AlgorithmConfig(**cfg)

    return SystemConfig(
        server=server,
        user_backend=user_backend,
        zlm=zlm,
        inference_server=inference_server,
        streams=streams,
        algorithms=algorithms,
    )


def _config_path(settings) -> Path:
    data_dir = settings.storage.get("data_dir")
    return Path(data_dir) / "system_config.json"


def load_system_config() -> SystemConfig:
    settings = load_settings()
    default = _build_default_config(settings)
    cfg_path = _config_path(settings)
    if not cfg_path.exists():
        return default
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            overrides = json.load(f)
    except Exception:
        return default

    data = default.dict()
    _deep_merge(data, overrides)
    return SystemConfig.parse_obj(data)


def save_system_config(cfg: SystemConfig) -> None:
    settings = load_settings()
    cfg_path = _config_path(settings)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(cfg.dict(), f, ensure_ascii=False, indent=2)
