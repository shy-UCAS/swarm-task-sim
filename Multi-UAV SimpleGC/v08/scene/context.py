"""场景上下文：读入登记的场景族、校验哈希与显式圈层几何、建距离场并缓存（V8-12 第 2 部分）。

核心构建不导入 shapely，也不导入 scene_v07（其包 __init__ 会导入 shapely）。可视图只在
visibility.py 的函数内部惰性导入。读入只读：不改输入文件的内容、大小和 mtime。
缓存只写调用方给的 cache_dir，且拒绝落在仓库、冻结工作树或任何 v07_* 路径下。
"""
import hashlib
import json
import math
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from ..config import load_config
from ..contract.monitoring import ContractInvalid, family_from_initial
from .exact import center_of_geometry, expand, kind_of
from .field import build_distance_field, conservative_cells, geometry_key

GEOMETRY_VERSION = "v08-scene-exact-1"
ADAPTER_VERSION = "v08-visibility-adapter-1"
LAYERS = ("protected", "alert", "warning")
_GEOMETRY_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "generator" / "geometry_v07_r1.json"
INPUT_FILES = ("public_scene.json", "family_initial.json", "check_results.json", "provenance.json")


class InputError(ValueError):
    """输入 SHA256 不符、引用错或显式几何与定义不一致（P0：输入与标签正确）。"""


@dataclass(frozen=True)
class Facility:
    id: str
    geometry: dict
    center: tuple
    layers: dict          # 层名 -> 显式几何
    offsets: dict         # 层名 -> offset_m


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def load_geometry_config():
    """geometry_v07_r1.json 只读加载：返回本项用到的余量。"""
    g = json.loads(_GEOMETRY_CONFIG.read_text(encoding="utf-8"))
    return {k: float(g[k]) for k in ("world_margin_m", "obstacle_margin_m", "forbidden_margin_m",
                                     "alignment_length_m", "pre_entry_warning_clearance_m")} | {
        "collection_clearance_m": tuple(float(x) for x in g["collection_clearance_m"]),
        "monitoring": dict(g["monitoring"]), "shape_attempts": int(g["shape_attempts"])}


def _check_layers(facility_entity, zones):
    """显式圈层几何必须等于 设施几何 + offset_m（V8-11 冻结核验用后一表示）。"""
    f = facility_entity["geometry"]
    got = {}
    for z in zones:
        layer = z.get("layer")
        if layer not in LAYERS or layer in got:
            raise InputError(f"设施 {facility_entity['id']} 的圈层 {layer!r} 缺失或重复")
        got[layer] = z
    if set(got) != set(LAYERS):
        raise InputError(f"设施 {facility_entity['id']} 缺少圈层：{sorted(set(LAYERS) - set(got))}")
    for layer, z in got.items():
        defined = expand(f, float(z["offset_m"]))
        explicit = z["geometry"]
        ok = kind_of(defined) == kind_of(explicit)
        if ok and kind_of(defined) == "Circle":
            ok = (np.max(np.abs(np.asarray(defined["center_m"], float) - np.asarray(explicit["center_m"], float))) <= 1e-9
                  and abs(defined["radius_m"] - explicit["radius_m"]) <= 1e-9)
        elif ok:
            ok = (np.asarray(defined["vertices_m"], float).shape == np.asarray(explicit["vertices_m"], float).shape
                  and np.max(np.abs(np.asarray(defined["vertices_m"], float) - np.asarray(explicit["vertices_m"], float))) <= 1e-9
                  and abs(defined["buffer_m"] - explicit["buffer_m"]) <= 1e-9)
        if not ok:
            raise InputError(f"设施 {facility_entity['id']} 的 {layer} 层显式几何与 设施几何 + offset_m 不一致："
                             f"显式={explicit!r} 定义={defined!r}")
    return got


class _DiskRaw:
    """{geometry_key: sdf 数组} 的可写映射，按需读写缓存目录下的 NPZ。"""

    def __init__(self, directory):
        self.directory = None if directory is None else Path(directory)
        self.mem = {}
        self.hits = 0
        self.misses = 0

    def _path(self, key):
        return self.directory / f"sdf_{key}.npz"

    def get(self, key, default=None):
        if key in self.mem:
            return self.mem[key]
        if self.directory is not None and self._path(key).exists():
            with np.load(self._path(key)) as z:
                arr = z["sdf"]
            self.mem[key] = arr
            self.hits += 1
            return arr
        return default

    def __setitem__(self, key, arr):
        self.misses += 1
        self.mem[key] = arr
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self._path(key).with_suffix(".tmp.npz")
            np.savez_compressed(tmp, sdf=arr)
            tmp.replace(self._path(key))


class SceneContext:
    def __init__(self, scene, family, facilities, obstacles, world, geometry_sha256, cache_key, cache_dir, params,
                 inputs=None):
        self.scene = scene
        self.family = family
        self.facilities = facilities                     # 按 id 排序
        self.zones = {f.id: f.layers for f in facilities}
        self.obstacles = obstacles                       # ((id, geometry), ...) 按 id 排序
        self.world = world
        self.geometry_sha256 = geometry_sha256
        self.cache_key = cache_key
        self.params = params                             # 来自冻结几何配置与 monitoring.json 的余量
        self.inputs = inputs or {}
        xs = np.array([p[0] for p in world["vertices_m"]], float)
        ys = np.array([p[1] for p in world["vertices_m"]], float)
        self.bounds = (float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()))
        self.fields = {}                                 # 阶段名 -> DistanceField（惰性）
        self.cell_sets = {}
        self.cache_dir = None if cache_dir is None else Path(cache_dir)
        self._raw = _DiskRaw(None if cache_dir is None else self.cache_dir / self.cache_key)
        self.timings = {}
        self.extra = {}

    @property
    def facility_by_id(self):
        return {f.id: f for f in self.facilities}

    @contextmanager
    def cold_build(self):
        """惰性缓存（距离场、可视图、边界点）的首次构建计时，累计到 timings["cold_s"]。
        规划耗时按"总用时 − 冷缓存用时"报告（指令 4.2：冷缓存另报，不混入每段耗时）。嵌套只计最外层。"""
        depth = self.timings.get("_depth", 0)
        self.timings["_depth"] = depth + 1
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.timings["_depth"] = depth
            if depth == 0:
                self.timings["cold_s"] = self.timings.get("cold_s", 0.0) + time.perf_counter() - t0
                self.timings["cold_builds"] = self.timings.get("cold_builds", 0) + 1

    def field(self, name, constraints):
        """阶段距离场：同名只建一次；各阶段共享同一几何的精确距离（并落盘）。"""
        if name not in self.fields:
            with self.cold_build():
                self.fields[name] = build_distance_field(constraints, self.bounds, spacing_m=self.params["grid_m"],
                                                         raw_cache=self._raw)
        return self.fields[name]

    def combined(self, name, constraints):
        """阶段组合栅格（约束取最小值），同名只建一次。"""
        from .field import CombinedGrid

        if ("grid", name) not in self.extra:
            with self.cold_build():
                self.extra[("grid", name)] = CombinedGrid(self.field(name, constraints))
        return self.extra[("grid", name)]

    def cells(self, key, field, *, names=None, extra_margin_m=0.0):
        k = (key, extra_margin_m)
        if k not in self.cell_sets:
            self.cell_sets[k] = conservative_cells(field, names=names, extra_margin_m=extra_margin_m)
        return self.cell_sets[k]

    def cache_stats(self):
        return {"hits": self._raw.hits, "misses": self._raw.misses}


def context_params():
    """本项几何/栅格参数：冻结几何配置 + configs/v08/monitoring.json。"""
    g = load_geometry_config()
    m = load_config("monitoring").values
    return {**g, "grid_m": m["grid_m"], "curve_spacing_m": m["curve_spacing_m"],
            "tracking_tube_m": m["tracking_tube_m"]}


def build_context(scene, family, *, cache_dir=None, inputs=None):
    params = context_params()
    entities = scene["entities"]
    ids = [e["id"] for e in entities]
    if len(set(ids)) != len(ids):
        raise InputError("场景实体 id 重复")
    world = scene["world"]["geometry"]
    if kind_of(world) != "Polygon":
        raise InputError("world 须为凸多边形")
    facs = sorted((e for e in entities if e["type"] == "facility"), key=lambda e: e["id"])
    if not facs:
        raise InputError("场景没有设施")
    zones_by_fac = {}
    for z in entities:
        if z["type"] == "protection_zone":
            if z.get("facility_id") not in {f["id"] for f in facs}:
                raise InputError(f"保护圈 {z['id']} 引用了不存在的设施 {z.get('facility_id')!r}")
            zones_by_fac.setdefault(z["facility_id"], []).append(z)
    facilities = []
    for f in facs:
        layers = _check_layers(f, zones_by_fac.get(f["id"], []))
        facilities.append(Facility(f["id"], f["geometry"], center_of_geometry(f["geometry"]),
                                   {k: v["geometry"] for k, v in layers.items()},
                                   {k: float(v["offset_m"]) for k, v in layers.items()}))
    obstacles = tuple((e["id"], e["geometry"]) for e in sorted(
        (e for e in entities if e["type"] == "hard_constraint_obstacle"), key=lambda e: e["id"]))
    geo = {"world": world, "facilities": [[f.id, f.geometry, {k: f.layers[k] for k in LAYERS}] for f in facilities],
           "obstacles": [[i, g] for i, g in obstacles]}
    geometry_sha = sha256_bytes(_canonical(geo).encode("utf-8"))
    key_doc = {"geometry": geo, "geometry_version": GEOMETRY_VERSION, "grid_m": params["grid_m"],
               "interpolation": "bilinear-minus-half-diagonal", "adapter_version": ADAPTER_VERSION,
               "margins": {k: params[k] for k in ("world_margin_m", "obstacle_margin_m", "forbidden_margin_m",
                                                   "pre_entry_warning_clearance_m", "alignment_length_m")},
               "monitoring": params["monitoring"], "collection_clearance_m": list(params["collection_clearance_m"])}
    cache_key = sha256_bytes(_canonical(key_doc).encode("utf-8"))
    return SceneContext(scene, family, tuple(facilities), obstacles, world, geometry_sha, cache_key, cache_dir, params,
                        inputs)


def _read_input(directory, name):
    path = directory / name
    raw = path.read_bytes()
    return raw, sha256_bytes(raw)


def load_context(entry, *, data_root, cache_dir):
    """读登记清单的一项：核对 public_scene.json 与 family_initial.json 的 SHA256，建上下文。
    四个输入文件只读；check_results.json、provenance.json 只记哈希作证据。"""
    root = Path(data_root)
    rel = PurePosixPath(entry["directory_rel"])
    # 数据根下的目录常是指向别处盘符的联接（如 v07_scene），所以按相对路径字面检查，不 resolve。
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise InputError(f"directory_rel 必须是数据根下的相对路径：{entry['directory_rel']!r}")
    directory = root.joinpath(*rel.parts)
    raws, shas = {}, {}
    for name in INPUT_FILES:
        raws[name], shas[name] = _read_input(directory, name)
    if shas["public_scene.json"] != entry["public_scene_sha256"]:
        raise InputError(f"{entry['family_id']} 的 public_scene.json SHA256 与登记不符")
    if shas["family_initial.json"] != entry["family_initial_sha256"]:
        raise InputError(f"{entry['family_id']} 的 family_initial.json SHA256 与登记不符")
    scene = json.loads(raws["public_scene.json"].decode("utf-8"))
    initial = json.loads(raws["family_initial.json"].decode("utf-8"))
    try:
        family = family_from_initial(entry["family_id"], initial)
    except ContractInvalid as exc:
        raise InputError(str(exc)) from None
    inputs = {"directory_rel": entry["directory_rel"], "sha256": shas}
    return build_context(scene, family, cache_dir=cache_dir, inputs=inputs)
