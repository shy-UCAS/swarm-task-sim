"""Read-only ENU episode plots; no simulation, reanalysis or CSV fallback."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from swarm_sim.episode_loader import load_episode, load_public_scene
from swarm_sim.generation import checked_path

VIZ_ROOT = ROOT.parent.parent / "SwarmData" / "viz"
COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def discover_episodes(source):
    """Accept an episode, example directory, dataset, or finalized batch."""
    source = Path(source).resolve()
    if (source / "manifest.json").is_file():
        paths = [source]
    else:
        dataset = source / "dataset" if (source / "dataset/dataset_manifest.json").is_file() else source
        manifest = dataset / "dataset_manifest.json"
        if manifest.is_file():
            paths = [checked_path(dataset, entry["directory"])
                     for entry in read_json(manifest)["episodes"]]
        else:
            base = source / "episodes" if (source / "episodes").is_dir() else source
            paths = sorted(p.parent for p in base.glob("*/manifest.json"))
    if not paths:
        raise ValueError(f"No episodes found: {source}")
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate episode directories in the dataset manifest")
    return paths


def load_plot_episode(path):
    data = load_episode(path)  # Keep all loader hash and protocol checks enabled.
    corners = load_public_scene(path)
    # The loader verified task.json. Select only scene context, never trajectories.
    scene = read_json(path / "task.json").get("scenario", {})
    return dict(path=path, data=data, corners=corners, world=scene.get("world", {}),
                restricted_regions=scene.get("restricted_regions", []))


def original_splits(paths):
    splits = {}
    for parent in sorted({p.parent for p in paths}):
        index = parent / "sample_index.json"
        if index.is_file():
            for sample in read_json(index).get("samples", []):
                splits[parent / sample["run_id"]] = sample.get("original_split")
    return splits


def filename(prefix, identity):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(identity)).strip("._")
    if not safe:
        raise ValueError(f"Cannot name a plot for {identity!r}")
    return f"{prefix}_{safe}.png"


def check_output(source, output):
    output = Path(output).resolve()
    viz_root = VIZ_ROOT.resolve()
    if output == viz_root or not output.is_relative_to(viz_root):
        raise ValueError(f"Output must be a subdirectory of {viz_root}")
    protected = (Path(source).resolve(), ROOT.parent.resolve(),
                 (ROOT.parent.parent / "Simulation").resolve())
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise ValueError("Output must be separate from the source and project archives")
    return output


def flag(value):
    return "yes" if value is True else "no" if value is False else "—"


def title(item):
    data = item["data"]
    labels, meta = data["targets"], data["metadata"]
    intent = labels.get("requested_intent") or labels.get("assigned_intent") or "—"
    success = labels.get("mission_success", meta.get("mission_success"))
    quality = meta.get("episode_quality_eligible")
    return (f"intent={intent} | plan={meta.get('flight_pattern') or '—'} | "
            f"success={flag(success)} | quality={flag(quality)}")


def rectangle(corners):
    xs, ys = zip(*corners)
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def plot_episode(ax, item, colors):
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D

    data, world = item["data"], item["world"]
    region_box = rectangle(item["corners"])
    label_span = max(region_box[2:])
    ax.add_patch(Rectangle(region_box[:2], *region_box[2:],
                           facecolor="#d4d4d4", edgecolor="#777777", alpha=.55, label="Target region"))
    if "east_bounds_m" in world and "north_bounds_m" in world:
        east, north = world["east_bounds_m"], world["north_bounds_m"]
        label_span = max(label_span, east[1] - east[0], north[1] - north[0])
        ax.add_patch(Rectangle((east[0], north[0]), east[1] - east[0], north[1] - north[0],
                               fill=False, edgecolor="#888888", linestyle="--", label="World boundary (context)"))
    for index, region in enumerate(item["restricted_regions"]):
        if region.get("type") != "rectangle":
            raise ValueError("Restricted region has no supported rectangle geometry")
        ax.add_patch(Rectangle((region["min_east_m"], region["min_north_m"]),
                               region["width_m"], region["height_m"], fill=False,
                               edgecolor="#b22222", hatch="///",
                               label="Restricted region (context)" if index == 0 else None))
    has_valid = False
    for index, agent in enumerate(data["agent_ids"]):
        valid = [row[index] for row in data["mask"]]
        # NaNs break lines at every false mask, including zero-filled missing rows.
        east = [row[index][0] if ok else float("nan") for row, ok in zip(data["x"], valid)]
        north = [row[index][1] if ok else float("nan") for row, ok in zip(data["x"], valid)]
        ax.plot(east, north, color=colors[agent], linewidth=1.7, label=agent)
        indices = [i for i, ok in enumerate(valid) if ok]
        if not indices:
            continue
        has_valid = True
        start = east[indices[0]], north[indices[0]]
        for stamp, marker, label in ((indices[0], "o", "start"), (indices[-1], "x", "end")):
            point = east[stamp], north[stamp]
            ax.plot(*point, marker=marker, color=colors[agent], markersize=6, linestyle="None")
            # A nearby return endpoint shares the ID label; both markers remain.
            if label == "end" and max(abs(a - b) for a, b in zip(point, start)) < .025 * label_span:
                continue
            side = 1 if index % 2 == 0 else -1
            offset = (8 * side, 9 + 7 * (index // 2) if label == "start" else -13 - 7 * (index // 2))
            ax.annotate(agent, point, xytext=offset, textcoords="offset points",
                        ha="left" if side == 1 else "right", fontsize=7, color=colors[agent])
    if not has_valid:
        ax.text(.5, .5, "No valid observations", transform=ax.transAxes, ha="center", va="center")
    labels, meta = data["targets"], data["metadata"]
    failed = (labels.get("mission_success", meta.get("mission_success")) is False
              or meta.get("episode_quality_eligible") is False or labels.get("run_status") == "failed")
    ax.set_title(title(item), fontsize=9, color="#b22222" if failed else "#222222", pad=12)
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=.18)
    handles, names = ax.get_legend_handles_labels()
    handles += [Line2D([], [], marker="o", linestyle="None", color="#444444"),
                Line2D([], [], marker="x", linestyle="None", color="#444444")]
    ax.legend(handles, names + ["First valid observation", "Last valid observation"],
              loc="upper right", fontsize=7, framealpha=.85)


def render(items, output, heading, show_split=False, splits=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    agents = sorted({agent for item in items for agent in item["data"]["agent_ids"]})
    colors = {agent: COLORS[i % len(COLORS)] for i, agent in enumerate(agents)}
    figure, axes = plt.subplots(1, len(items), figsize=(8 * len(items), 8),
                                squeeze=False, sharex=True, sharey=True)
    try:
        bounds = []
        for ax, item in zip(axes[0], items):
            plot_episode(ax, item, colors)
            identity = item["data"]["metadata"].get("run_id") or item["path"].name
            if show_split:
                split = item["data"]["metadata"].get("split")
                if split is not None:
                    identity += f" · split={split}"
                else:
                    identity += f" · original split={(splits or {}).get(item['path']) or '—'}"
            ax.text(.5, -.11, identity, transform=ax.transAxes, ha="center", fontsize=9)
            # Collect each panel's data bounds explicitly; shared axes use their union.
            bounds.append(ax.dataLim.extents)
        xmin = min(b[0] for b in bounds); ymin = min(b[1] for b in bounds)
        xmax = max(b[2] for b in bounds); ymax = max(b[3] for b in bounds)
        pad = .05 * max(xmax - xmin, ymax - ymin, 1)
        for ax in axes[0]:
            ax.set_xlim(xmin - pad, xmax + pad)
            ax.set_ylim(ymin - pad, ymax + pad)
        figure.suptitle(heading, fontsize=12)
        figure.tight_layout(rect=(0, .04, 1, .96))
        # Exclusive creation prevents a rerun from replacing an existing picture.
        with Path(output).open("xb") as stream:
            figure.savefig(stream, format="png", dpi=160)
    finally:
        plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Episode, examples, dataset, or finalized batch")
    parser.add_argument("--out", type=Path, help="New output directory under SwarmData/viz")
    parser.add_argument("--family", nargs="?", const="*", metavar="ID",
                        help="Also plot families side by side; an ID selects only that family")
    parser.add_argument("--show-split", action="store_true", help="Show frozen split (sample_index.json for examples)")
    args = parser.parse_args(argv)
    try:
        paths = discover_episodes(args.source)
        groups = defaultdict(list)
        for path in paths:
            family = read_json(path / "manifest.json").get("family_id")
            if family:
                groups[family].append(path)
        if args.family not in (None, "*"):
            if args.family not in groups:
                raise ValueError(f"Unknown family: {args.family}")
            paths = groups[args.family]
            groups = {args.family: paths}
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = check_output(args.source, args.out or VIZ_ROOT / f"{args.source.resolve().name}_{timestamp}")
        names = [filename("episode", p.name) for p in paths]
        if args.family is not None:
            names += [filename("family", family) for family in groups]
        if len(set(names)) != len(names):
            raise ValueError("Plot filenames collide")
        for name in names:
            if (output / name).exists():
                raise FileExistsError(f"Plot already exists; choose another output directory: {output / name}")
        splits = original_splits(paths) if args.show_split else {}
        output.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    errors, count = [], 0
    available = set()
    for path in paths:
        try:
            item = load_plot_episode(path)
            render([item], output / filename("episode", path.name), path.name, args.show_split, splits)
            available.add(path)
            count += 1
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    if args.family is not None:
        for family, members in groups.items():
            if not all(p in available for p in members):
                errors.append(f"{family}: family plot omitted because an episode could not be loaded")
                continue
            try:
                items = [load_plot_episode(p) for p in members]
                render(items, output / filename("family", family), f"family={family}", args.show_split, splits)
                count += 1
            except (OSError, ValueError) as exc:
                errors.append(f"{family}: {exc}")
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Saved {count} PNG(s) to {output}; errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
