"""Passive source-clock audit and offline onboard SIM truth extraction.

The fit maps FCU boot time to host *receive* time, not an identified transport-
delay-free clock. Residuals are diagnostics, never synchronization guarantees.
"""

import bisect
import csv
import math
import statistics
from pathlib import Path

from .scenario import geo_to_enu


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    x = (len(values) - 1) * fraction
    left = int(x)
    return values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (x - left)


def fit_clock(pairs):
    """Piecewise 1-second medians with an affine trend; audit on held-out samples."""
    info = dict(method="passive_SYSTEM_TIME_piecewise_1s_medians_with_heldout_audit", available=False,
                transport_delay_identified=False, absolute_alignment_bound_s=None,
                warning="residuals include scheduling/transport jitter; not a clock accuracy bound")
    if any(b[0] < a[0] or b[1] < a[1] for a, b in zip(pairs, pairs[1:])):
        return dict(info, reason="source or receive clock reset/nonmonotonic")
    if any(b[0] - a[0] > 2 or b[1] - a[1] > 2 for a, b in zip(pairs, pairs[1:])):
        return dict(info, reason="clock evidence gap exceeds 2 seconds")
    if len(pairs) < 20 or pairs[-1][0] - pairs[0][0] < 5:
        return dict(info, reason="need >=20 samples spanning >=5 source seconds")
    bins = {}
    for source, host in pairs[::2]:
        bins.setdefault(math.floor(source), []).append((source, host))
    centers = [(statistics.median(p[0] for p in group), statistics.median(p[1] for p in group))
               for group in bins.values()]
    mx, my = statistics.mean(p[0] for p in centers), statistics.mean(p[1] for p in centers)
    denominator = sum((x - mx) ** 2 for x, _ in centers)
    slope = sum((x - mx) * (y - my) for x, y in centers) / denominator
    if not 0.5 <= slope <= 2:
        return dict(info, reason="source/host rate outside supported speedup=1 range")
    offset = my - slope * mx
    residuals = [host - (slope * source + offset) for source, host in pairs]
    if any(not 0.5 <= (b[1] - a[1]) / (b[0] - a[0]) <= 2 for a, b in zip(centers, centers[1:])):
        return dict(info, reason="local source/host rate outside supported speedup=1 range")
    model = dict(knots=centers, available=True)
    heldout = [abs(host - clock_to_host(source, model)) for source, host in pairs[1::2]
               if centers[0][0] <= source <= centers[-1][0]]
    return dict(info, available=True, samples=len(pairs), bins=len(centers), slope=slope,
                offset_s=offset, rate_difference_ppm=(slope - 1) * 1e6,
                affine_receive_residual_abs_p95_s=percentile([abs(r) for r in residuals], 0.95),
                source_range_s=[centers[0][0], centers[-1][0]], knots=centers,
                heldout_samples=len(heldout), receive_residual_abs_p95_s=percentile(heldout, 0.95),
                receive_residual_abs_max_s=max(heldout),
                audit="fit even-index samples, evaluate odd-index samples; 1s median knots; no extrapolation")


def clock_to_host(source, model):
    knots = model["knots"]
    if not knots[0][0] <= source <= knots[-1][0]:
        raise ValueError("clock mapping does not extrapolate")
    index = max(1, bisect.bisect_left([p[0] for p in knots], source))
    a, b = knots[index - 1], knots[index]
    weight = (source - a[0]) / (b[0] - a[0])
    return a[1] + weight * (b[1] - a[1])


def read_truth(directory, agent, origin):
    """Return SIM ENU poses and effective PARM values, preserving source times."""
    from pymavlink import DFReader
    paths = sorted((Path(directory) / "sitl" / agent / "logs").glob("*.BIN"))
    # One fresh SITL per run should produce one BIN; do not silently merge resets.
    if len(paths) != 1:
        return [], {}, dict(available=False, reason=f"expected one BIN, found {len(paths)}")
    reader = DFReader.DFReader_binary(str(paths[0]))
    samples, parameters = [], {}
    dropped = 0
    try:
        while True:
            message = reader.recv_match(type=["SIM", "PARM"])
            if message is None:
                break
            if message.get_type() == "PARM":
                value = float(message.Value)
                parameters[str(message.Name)] = value if math.isfinite(value) else None
                continue
            packet = message.to_dict()
            source = packet["TimeUS"] / 1e6
            values = [*geo_to_enu(packet["Lat"], packet["Lng"], packet["Alt"], origin),
                      packet["Q1"], packet["Q2"], packet["Q3"], packet["Q4"]]
            if not all(math.isfinite(v) for v in [source, *values]):
                dropped += 1
                continue
            if samples and source <= samples[-1][0]:
                return [], parameters, dict(available=False, reason="SIM source timestamp reset/duplicate")
            samples.append((source, values))
    finally:
        reader.close()
    return samples, parameters, dict(available=bool(samples), source="onboard_BIN_SIM",
        path=str(paths[0].relative_to(directory)), samples=len(samples), dropped_nonfinite=dropped,
        fields="ENU position and wxyz quaternion; no ground-truth velocity available",
        parameter_source="BIN PARM; last logged value, not a guaranteed complete live snapshot")


def write_csv(path, fields, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        writer.writerows(rows)
