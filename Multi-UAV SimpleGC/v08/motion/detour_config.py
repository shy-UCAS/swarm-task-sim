"""V8-21 迂回候选判据配置的专用加载器（指令 2.1、12.3；裁定附录接受）。

冻结 v08.config.load_config 只接受有限数值，不能读本文件里的字符串参数 sweep_measure，也不得放宽它。本模块对同一
v08-config-v1 纪律单独校验：顶层恰三键、参数恰五键、每项恰 value/kind/source；只对 sweep_measure 接受字符串且必须为
"span"；其余为有限数（排除 bool）。目标层必须为 0，D 正，Θ 正且小于排他上限，排他上限等于 360。空值或错误类型报
"配置未就绪"，不回退任何默认值。

kind 允许冻结 KINDS 加 "measured"（2026-11-11 候选取值补充裁定第 1 节把两项状态从 pending_measurement 改为 measured）；
kind 为 pending_measurement 的项必须已经填值，否则同样是配置未就绪。

导入时不读文件。
"""
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from ..config import CONFIG_DIR, KINDS, SCHEMA

NAME = "criteria_detour_candidate"
PARAMETERS = ("max_target_layer_detour", "near_band_width_m", "min_sweep_deg", "max_sweep_deg_exclusive",
              "sweep_measure")
CANDIDATE_KINDS = tuple(KINDS) + ("measured",)
STRING_PARAMETERS = {"sweep_measure": ("span",)}


class CandidateConfigNotReady(ValueError):
    """候选配置缺值、类型错误或不满足定义关系（配置未就绪，不是普通几何失败）。"""


@dataclass(frozen=True)
class LoadedCandidate:
    name: str
    path: str
    sha256: str
    values: dict
    kinds: dict


def load_detour_candidate(config_dir=None):
    path = Path(config_dir if config_dir is not None else CONFIG_DIR) / f"{NAME}.json"
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateConfigNotReady(f"{path}: 不是 UTF-8 JSON：{exc}") from None
    if not isinstance(doc, dict) or set(doc) != {"schema", "name", "parameters"}:
        raise CandidateConfigNotReady(f"{path}: 顶层键必须恰为 schema、name、parameters")
    if doc["schema"] != SCHEMA or doc["name"] != NAME:
        raise CandidateConfigNotReady(f"{path}: schema/name 应为 {SCHEMA}/{NAME}")
    params = doc["parameters"]
    if not isinstance(params, dict) or set(params) != set(PARAMETERS):
        raise CandidateConfigNotReady(f"{path}: parameters 必须恰为 {PARAMETERS}")
    values, kinds = {}, {}
    for key in PARAMETERS:
        entry = params[key]
        if not isinstance(entry, dict) or set(entry) != {"value", "kind", "source"}:
            raise CandidateConfigNotReady(f"{path}: 参数 {key} 的键必须恰为 value、kind、source")
        if entry["kind"] not in CANDIDATE_KINDS:
            raise CandidateConfigNotReady(f"{path}: 参数 {key} 的 kind {entry['kind']!r} 不在 {CANDIDATE_KINDS}")
        if not isinstance(entry["source"], str) or not entry["source"].strip():
            raise CandidateConfigNotReady(f"{path}: 参数 {key} 缺少 source")
        value = entry["value"]
        if key in STRING_PARAMETERS:
            if not isinstance(value, str) or value not in STRING_PARAMETERS[key]:
                raise CandidateConfigNotReady(f"{path}: 参数 {key} 必须是 {STRING_PARAMETERS[key]} 之一")
            values[key] = value
        else:
            if value is None:
                raise CandidateConfigNotReady(f"{path}: 参数 {key} 尚未填值（配置未就绪）")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CandidateConfigNotReady(f"{path}: 参数 {key} 的 value 必须是有限数")
            values[key] = float(value)
        kinds[key] = entry["kind"]
    if values["max_target_layer_detour"] != 0.0:
        raise CandidateConfigNotReady(f"{path}: max_target_layer_detour 必须为 0")
    if not values["near_band_width_m"] > 0.0:
        raise CandidateConfigNotReady(f"{path}: near_band_width_m 必须为正")
    if values["max_sweep_deg_exclusive"] != 360.0:
        raise CandidateConfigNotReady(f"{path}: max_sweep_deg_exclusive 必须等于 360")
    if not (0.0 < values["min_sweep_deg"] < values["max_sweep_deg_exclusive"]):
        raise CandidateConfigNotReady(f"{path}: min_sweep_deg 必须为正且小于排他上限")
    return LoadedCandidate(NAME, str(path), hashlib.sha256(raw).hexdigest(), values, kinds)
