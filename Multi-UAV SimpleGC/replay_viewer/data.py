"""Read-only replay data, on the recorder's run-relative host clock.

samples.csv covers preparation/takeoff/mission/landing. It is deliberately not
replaced with the narrower, differently originated observations.csv grid.
"""

import bisect
import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


@dataclass
class Sample:
    t: float
    valid: bool
    xyz: tuple
    speed: float | None
    mode: str
    armed: str
    reason: str = ""


@dataclass
class Track:
    samples: list = field(default_factory=list)
    times: list = field(default_factory=list)

    def at(self, t, max_gap):
        index = bisect.bisect_right(self.times, t) - 1
        if index < 0:
            return None
        sample = self.samples[index]
        if not sample.valid or t - sample.t > max_gap:
            return None
        return sample

    def plot_points(self, max_gap):
        """NaN barriers stop plot lines reconnecting missing/invalid evidence."""
        times, east, north, up = [], [], [], []
        previous = None
        for sample in self.samples:
            if previous is not None and sample.t - previous > max_gap:
                times.append(previous)
                east.append(math.nan)
                north.append(math.nan)
                up.append(math.nan)
            times.append(sample.t)
            xyz = sample.xyz if sample.valid else (math.nan,) * 3
            east.append(xyz[0])
            north.append(xyz[1])
            up.append(xyz[2])
            previous = sample.t
        return times, east, north, up


@dataclass
class Replay:
    path: Path
    scene: dict
    metadata: dict = field(default_factory=dict)
    tracks: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    quality: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    analysis_name: str = ""
    is_run: bool = False
    duration: float = 0.0

    @property
    def agent_ids(self):
        return [v["id"] for v in self.scene["vehicles"]]

    @property
    def max_gap(self):
        return self.scene["max_gap_s"]

    @property
    def mission_start(self):
        return next((e["t"] for e in self.events if e.get("event") == "phase_start_sent"), 0.0)


def load_replay(path):
    from swarm_sim.scenario import validate
    from swarm_sim.tasks import compile_task, validate_task_binding

    path = Path(path).resolve()
    if path.is_file() and path.name in ("metadata.json", "samples.csv"):
        path = path.parent
    if path.is_file():
        source = read_json(path)
        scene = validate(source if "phases" in source else compile_task(source))
        validate_task_binding(scene)
        return Replay(path=path, scene=scene)
    if not path.is_dir():
        raise ValueError(f"文件或目录不存在：{path}")
    metadata = read_json(path / "metadata.json")
    if metadata.get("status") == "running":
        raise ValueError("这是仍标记为 running 的目录。当前界面只回放已结束的运行。")
    original = read_json(path / "scenario.json")
    if metadata.get("scenario") != original:
        raise ValueError("scenario.json 与 metadata 中保存的场景不一致。")
    scene = validate(original)
    replay = Replay(path=path, scene=scene, metadata=metadata, is_run=True)
    replay.tracks = {agent: Track() for agent in replay.agent_ids}
    samples_path = path / "samples.csv"
    invalid_values = 0
    if samples_path.exists():
        with samples_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"t", "agent_id", "valid_position", "east_m", "north_m", "up_m"}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError("samples.csv 缺少回放所需的时间、身份或位置列。")
            for line, row in enumerate(reader, 2):
                agent, t = row.get("agent_id"), number(row.get("t"))
                if agent not in replay.tracks or t is None or t < 0:
                    raise ValueError(f"samples.csv 第 {line} 行身份或时间无效。")
                track = replay.tracks[agent]
                if track.times and t <= track.times[-1]:
                    raise ValueError(f"samples.csv 第 {line} 行同一飞机时间重复或倒退。")
                xyz = tuple(number(row.get(k)) for k in ("east_m", "north_m", "up_m"))
                valid = row.get("valid_position") == "1" and all(v is not None for v in xyz)
                if row.get("valid_position") == "1" and not valid:
                    invalid_values += 1
                velocity = [number(row.get(k)) for k in ("ve_m_s", "vn_m_s", "vu_m_s")]
                speed = math.hypot(*velocity) if all(v is not None for v in velocity) else None
                track.samples.append(Sample(t, valid, xyz, speed, row.get("mode", ""),
                                            row.get("armed", ""), row.get("position_invalid_reason", "")))
                track.times.append(t)
    else:
        replay.warnings.append("缺少 samples.csv，仅显示计划和已保存的结果。")
    if invalid_values:
        replay.warnings.append(f"{invalid_values} 行宣称有效但数值异常，已按无效位置处理。")
    events_path = path / "events.jsonl"
    if events_path.exists():
        with events_path.open(encoding="utf-8-sig") as stream:
            for line, text in enumerate(stream, 1):
                try:
                    event = json.loads(text)
                    t = number(event.get("t"))
                    if t is None or t < 0 or not isinstance(event.get("event"), str):
                        raise ValueError("invalid event")
                    event["t"] = t
                    replay.events.append(event)
                except (ValueError, AttributeError):
                    replay.warnings.append(f"事件日志第 {line} 行不完整或无效，未用于显示。")
        replay.events.sort(key=lambda e: e["t"])
    else:
        replay.warnings.append("缺少事件日志，阶段信息不可用。")
    ends = [track.times[-1] for track in replay.tracks.values() if track.times]
    ends += [e["t"] for e in replay.events]
    elapsed = number(metadata.get("elapsed_s"))
    if elapsed is not None and elapsed >= 0:
        ends.append(elapsed)
    replay.duration = max(ends, default=0.0)
    # Saved reports are optional and visibly distinguished from recomputation.
    pointer = path / "analysis_latest.json"
    if pointer.exists():
        try:
            relative = read_json(pointer)["directory"]
            analysis = (path / relative).resolve()
            if analysis.parent != path:
                raise ValueError("分析路径必须是当前运行的直接子目录")
            quality = read_json(analysis / "quality.json")
            labels = read_json(analysis / "labels.json")
            if not isinstance(quality, dict) or not isinstance(labels, dict):
                raise ValueError("质量与标签文件必须是 JSON 对象")
            replay.quality, replay.labels = quality, labels
            replay.analysis_name = analysis.name
        except (OSError, ValueError, TypeError, KeyError) as exc:
            replay.warnings.append(f"已保存分析未能读取：{exc}")
    return replay


def discover_runs(root):
    """Only project run roots; datasets are not independently flown runs."""
    found = []
    for name in ("runs", "verification"):
        base = Path(root) / name
        if base.exists():
            found.extend(p.parent for p in base.rglob("samples.csv") if (p.parent / "metadata.json").exists())
    return sorted(set(found), key=lambda p: p.name, reverse=True)
