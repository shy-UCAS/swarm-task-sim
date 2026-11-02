"""v0.8 配置读取：每个参数带取值、类别和来源说明（schema v08-config-v1）。"""
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

KINDS = ("definitional", "execution", "engineering_margin", "pending_measurement")
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs" / "v08"
SCHEMA = "v08-config-v1"


@dataclass(frozen=True)
class LoadedConfig:
    name: str
    path: str
    sha256: str
    values: dict
    kinds: dict


def load_config(name, *, config_dir=None) -> LoadedConfig:
    path = Path(config_dir if config_dir is not None else CONFIG_DIR) / f"{name}.json"
    raw = path.read_bytes()
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict) or set(doc) != {"schema", "name", "parameters"}:
        raise ValueError(f"{path}: 顶层键必须恰为 schema、name、parameters")
    if doc["schema"] != SCHEMA:
        raise ValueError(f"{path}: schema 应为 {SCHEMA}，实际 {doc['schema']!r}")
    if doc["name"] != name:
        raise ValueError(f"{path}: name {doc['name']!r} 与文件名不符")
    params = doc["parameters"]
    if not isinstance(params, dict):
        raise ValueError(f"{path}: parameters 必须是对象")
    values, kinds = {}, {}
    for key, entry in params.items():
        if not isinstance(entry, dict) or set(entry) != {"value", "kind", "source"}:
            raise ValueError(f"{path}: 参数 {key} 的键必须恰为 value、kind、source")
        if entry["kind"] not in KINDS:
            raise ValueError(f"{path}: 参数 {key} 的 kind {entry['kind']!r} 不在 {KINDS} 中")
        if not isinstance(entry["source"], str) or not entry["source"].strip():
            raise ValueError(f"{path}: 参数 {key} 缺少 source")
        value = entry["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{path}: 参数 {key} 的 value 必须是有限数")
        values[key] = float(value)
        kinds[key] = entry["kind"]
    return LoadedConfig(name, str(path), hashlib.sha256(raw).hexdigest(), values, kinds)
