"""S1 sampling/plotting entry point. This is the only S1 matplotlib importer."""
import argparse
import math
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as PlotPolygon, Patch

from scene_v07.batch import DEFAULT_OUTPUT_ROOT, generate_attempt
from scene_v07.contract import SceneConfig
from scene_v07.sampling_s11 import SamplingPolicy
from scene_v07.geometry import center_of, expand_geometry, polygon_parts, to_shape


def plot_family(scene, family, checks, path, index):
    if path.exists():
        raise FileExistsError(path)
    figure = plt.figure(figsize=(12.8, 10), facecolor="#f6f8fb")
    ax = figure.add_axes([.07, .10, .71, .80], facecolor="white")
    panel = figure.add_axes([.805, .10, .18, .80])
    panel.axis("off")
    entities = scene["entities"]
    colors = ["#24578c", "#8867aa", "#b97325"]
    facilities = [e for e in entities if e["type"] == "facility"]
    facility_colors = {f["id"]: colors[i] for i, f in enumerate(facilities)}
    bounds = [to_shape(scene["world"]["geometry"]).bounds]

    def area(geometry, facecolor, edgecolor, alpha=1, linewidth=1, linestyle="-", hatch=None, zorder=1):
        shape = to_shape(geometry)
        bounds.append(shape.bounds)
        for polygon in polygon_parts(shape):
            ax.add_patch(PlotPolygon(list(polygon.exterior.coords), facecolor=facecolor,
                                     edgecolor=edgecolor, alpha=alpha, linewidth=linewidth,
                                     linestyle=linestyle, hatch=hatch, zorder=zorder))
    # Draw the actual contour offsets (including polygon corners).
    for layer in ["warning", "alert", "protected"]:
        for entity in entities:
            if entity["type"] == "protection_zone" and entity["layer"] == layer:
                color = facility_colors[entity["facility_id"]]
                area(entity["geometry"], color, color, {"warning": .075, "alert": .13, "protected": .24}[layer],
                     linewidth={"warning": 1.2, "alert": 1.6, "protected": 1.9}[layer])
    for facility in facilities:
        area(facility["geometry"], facility_colors[facility["id"]], "#102136", zorder=7)
        center = center_of(facility["geometry"])
        ax.annotate("F" + facility["id"].split("_")[-1], center, xytext=(7, 7), textcoords="offset points",
                    weight="bold", fontsize=10, zorder=12)
    for entity in entities:
        if entity["type"] == "hard_constraint_obstacle":
            area(expand_geometry(entity["geometry"], family["config"]["safety_margin_m"]),
                 "none", "#66717e", linestyle="--", linewidth=1.1, zorder=5)
            area(entity["geometry"], "#d0d4db", "#35414f", hatch="///", zorder=6)
            ax.text(*center_of(entity["geometry"]), "X" + entity["id"].split("_")[-1],
                    ha="center", va="center", fontsize=9, zorder=10)
        elif entity["type"] == "radar":
            position = entity["geometry"]["position_m"]
            ax.scatter(*position, marker="D", color="#c84146", s=35, edgecolors="white", zorder=11)
    for entry in scene["entry_zones"]:
        area(entry["geometry"], "#62cbd7", "#007e92", alpha=.55, linewidth=1.4, zorder=8)
        ax.annotate("E" + entry["id"].split("_")[-1], center_of(entry["geometry"]),
                    xytext=(6, -16), textcoords="offset points", color="#006c80", weight="bold", zorder=12)
    for state in family["initial_states"]:
        ax.scatter(*state["position_enu_m"][:2], marker="^", s=16, color="#783c9c", zorder=10)
    for route in checks["routes"]:
        if route["points_m"]:
            points = route["points_m"]
            if route.get("straight_blocked_by_obstacle"):
                ax.plot([points[0][0],points[-1][0]],[points[0][1],points[-1][1]],
                        color="#c75a59",linestyle=":",linewidth=1,alpha=.7,zorder=4)
            ax.plot([p[0] for p in points], [p[1] for p in points],
                    color=facility_colors[route["facility_id"]], linewidth=1.7, alpha=.85, zorder=9)
    for approach in checks["approaches"]:
        samples = approach["samples"]
        for low, high in approach["arcs_deg"]:
            points = [sample["point_m"] for sample in samples if low <= sample["angle_deg"] < high]
            if low == 0 and high == 360:
                points.append(points[0])
            if points:
                ax.plot([p[0] for p in points], [p[1] for p in points], color="#228f64", linewidth=3.3, zorder=10)
                if len(points) == 1:
                    ax.scatter(*points[0], color="#228f64", s=12, zorder=10)
    world = to_shape(scene["world"]["geometry"])
    x, y = world.exterior.xy
    ax.plot(x, y, color="#182638", linewidth=1.8, zorder=13)
    minimum_x, minimum_y = min(b[0] for b in bounds), min(b[1] for b in bounds)
    maximum_x, maximum_y = max(b[2] for b in bounds), max(b[3] for b in bounds)
    ax.set_xlim(minimum_x - 100, maximum_x + 100)
    ax.set_ylim(minimum_y - 100, maximum_y + 100)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=.14, color="#73879a")
    ax.set_xlabel("East (m, ENU)")
    ax.set_ylabel("North (m, ENU)")
    ax.annotate("N", xy=(.95, .96), xytext=(.95, .86), xycoords="axes fraction",
                ha="center", weight="bold", arrowprops={"arrowstyle": "->", "color": "#182638"})
    accepted = checks["accepted"]
    figure.text(.07, .95, f"Traj2Language v0.7 / {family.get('sampling_revision', 's1').upper()}   |   candidate {index:03d}   |   {'ACCEPTED' if accepted else 'REJECTED'}",
                fontsize=16, weight="bold", color="#186344" if accepted else "#a33740")
    legend = [Patch(facecolor="#24578c", label="Facility contour"),
              Patch(facecolor="#e9edf5", edgecolor="#24578c", label="Warning (outer)"),
              Patch(facecolor="#d6dfed", edgecolor="#24578c", label="Alert (middle)"),
              Patch(facecolor="#b9cbe1", edgecolor="#24578c", label="Protected (inner)"),
              Patch(facecolor="#d0d4db", edgecolor="#35414f", hatch="///", label="Hard obstacle"),
              Line2D([], [], color="#66717e", linestyle="--", label="30 m clearance"),
              Line2D([], [], marker="D", color="#c84146", linestyle="none", label="Radar"),
              Patch(facecolor="#62cbd7", label="Entry zone"),
              Line2D([], [], marker="^", color="#783c9c", linestyle="none", label="Initial UAV"),
              Line2D([], [], color="#24578c", label="Example shortest route"),
              Line2D([], [], color="#c75a59",linestyle=":",label="Blocked direct line"),
              Line2D([], [], color="#228f64", linewidth=3, label="Feasible approach bins")]
    panel.legend(handles=legend, loc="upper left", frameon=False, fontsize=8.5, handlelength=2)
    ratios = [r["detour_ratio"] for r in checks["routes"] if r["detour_ratio"] is not None]
    details = [f"Layout: {family['layout']}", f"Map: {family['config']['map_side_m']/1000:.0f} km", f"Facilities: {len(facilities)}",
               f"UAVs: {family['vehicle_count']}", f"Speed: {family['cruise_speed_m_s']:.2f} m/s",
               f"Height: {family['task_altitude_m']:.1f} m", f"Routes: {len(ratios)}/{len(checks['routes'])}",
               f"Max detour ratio: {max(ratios, default=0):.3f}",
               f"Raw direct blocked: {sum(r.get('straight_blocked_by_obstacle',False) for r in checks['routes'])}/{len(checks['routes'])}",
               f"Max lateral: {max((r.get('max_lateral_deviation_m') or 0 for r in checks['routes']),default=0):.1f} m",
               "", "Approach span (diagnostic):"]
    details.extend(f"F{a['facility_id'].split('_')[-1]}: {a['available_span_deg']} deg" for a in checks["approaches"])
    details += ["", "Checks:"]
    codes = sorted({i["code"] for i in checks["issues"]})
    details.extend(codes if codes else ["all geometry/access gates pass"])
    panel.text(0, .59, "\n".join(details), va="top", fontsize=8.0, linespacing=1.4,
               color="#243447", wrap=True)
    figure.text(.07, .035, f"Family seed: {family['sampling_seed']}   |   5 deg sampled angular bins, all entries + clear inward leg",
                fontsize=9, color="#607080")
    figure.text(.07, .018, "Protection zones are semantic regions. Only independent hard obstacles affect routes.",
                fontsize=8.5, color="#607080")
    try:
        figure.savefig(path, dpi=120, facecolor=figure.get_facecolor())
    finally:
        plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=int, default=300)
    parser.add_argument("--seed", type=int, default=2026101307, help="Attempt master seed (audit-only)")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--attempt-name")
    parser.add_argument("--family-seed", type=int, help="Reconstruct one family; use --candidates 1")
    parser.add_argument("--sampling-revision", choices=["s1","s1.1","s1.2"],default="s1.1")
    parser.add_argument("--obstacle-attempts",type=int,default=48)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    def progress(done, total, record):
        if done == 1 or done % 15 == 0 or done == total:
            print(f"{done}/{total}: {'accepted' if record['accepted'] else 'rejected'}; seed={record['sampling_seed']}", flush=True)
    summary = generate_attempt(args.candidates, args.seed, args.output_root, args.attempt_name,
                               SceneConfig(), None if args.no_plots else plot_family, progress, args.family_seed, args.sampling_revision,
                               SamplingPolicy(obstacle_attempts=args.obstacle_attempts) if args.sampling_revision in ("s1.1","s1.2") else None)
    print(f"Output: {summary['attempt_directory']}")
    print(f"Accepted: {summary['accepted_count']}/{summary['candidate_count']}; rejection rate {summary['rejection_rate']:.2%}")
    print(f"Timing (s): {summary['timing_s']}")


if __name__ == "__main__":
    main()
