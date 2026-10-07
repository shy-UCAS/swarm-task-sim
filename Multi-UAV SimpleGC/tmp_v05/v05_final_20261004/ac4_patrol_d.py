"""Read-only extraction of the patrol-phase timing progress difference (AC4 D) for the
v0.5 final report.  Never writes into a run, analysis or ledger directory.

Sources (read-only):
  verification/v05_batch_20261002/control.json         batch records B001-B240
  verification/v05_r12b_pp_20261002/control.json       pilot records PP01-PP20
  <analysis_directory>/ac4_timing_v3.json              channels.<ch>.per_phase.<phase>.primary

Reported per channel (truth / observation) and per scope (batch / pilot / all):
  n, known D, unknown D, median, p95, max, D>tau count and fraction.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH_CONTROL = ROOT / "verification/v05_batch_20261002/control.json"
PILOT_CONTROL = ROOT / "verification/v05_r12b_pp_20261002/control.json"
PHASE_BY_INTENT = {"patrol": "p01_patrol", "reconnaissance": "p01_observe"}
CHANNELS = ("truth", "observation")


def records(path):
    return json.load(open(path, encoding="utf-8"))["records"]


def collect(rows, scope, phase="p01_patrol", intent="patrol"):
    out = []
    for r in rows:
        if r.get("intent") != intent:
            continue
        entry = dict(scope=scope, logical=r.get("logical_index"), run_id=r.get("run_id"),
                     quality=r.get("episode_quality_eligible"))
        ac4 = Path(r["analysis_directory"]) / "ac4_timing_v3.json"
        entry["ac4_present"] = ac4.exists()
        if ac4.exists():
            data = json.load(open(ac4, encoding="utf-8"))
            for ch in CHANNELS:
                node = (data.get("channels") or {}).get(ch) or {}
                prim = ((node.get("per_phase") or {}).get(phase) or {}).get("primary") or {}
                xc = (((node.get("v1_diagnostic") or {}).get("per_phase") or {}).get(phase)) or {}
                entry[ch + "_D_s"] = prim.get("D_s")
                entry[ch + "_tau_s"] = prim.get("tau_s")
                entry[ch + "_complete"] = prim.get("complete")
                entry[ch + "_within_tau"] = prim.get("within_tau")
                entry[ch + "_issues"] = prim.get("issues")
                entry[ch + "_cross_max_abs_s"] = xc.get("max_abs_s")
                entry[ch + "_cross_within_tau"] = xc.get("within_tau")
                entry[ch + "_cross_complete"] = xc.get("complete")
        out.append(entry)
    return out


def summarize(rows, channel):
    n = len(rows)
    known = [r for r in rows if r.get(channel + "_complete") is True
             and isinstance(r.get(channel + "_D_s"), (int, float))]
    values = sorted(r[channel + "_D_s"] for r in known)
    exceeded = [r for r in known if r.get(channel + "_within_tau") is False]
    within = [r for r in known if r.get(channel + "_within_tau") is True]
    unresolved = [r for r in known if r.get(channel + "_within_tau") is None]
    cross_known = [r for r in rows if isinstance(r.get(channel + "_cross_max_abs_s"), (int, float))]
    cross_exceeded = [r for r in cross_known if r.get(channel + "_cross_within_tau") is False]

    def p95(vals):
        if not vals:
            return None
        k = max(0, min(len(vals) - 1, int(round(0.95 * (len(vals) - 1)))))
        return vals[k]

    return dict(scope=f"{n} runs", runs=n, D_known=len(known), D_unknown=n - len(known),
                D_median_s=statistics.median(values) if values else None,
                D_p95_s=p95(values), D_max_s=max(values) if values else None,
                D_over_tau=len(exceeded), D_over_tau_fraction=len(exceeded) / len(known) if known else None,
                D_within_tau=len(within), D_within_tau_unresolved=len(unresolved),
                cross_known=len(cross_known), cross_over_tau=len(cross_exceeded),
                cross_over_tau_fraction=len(cross_exceeded) / len(cross_known) if cross_known else None,
                cross_max_abs_max_s=max((r[channel + "_cross_max_abs_s"] for r in cross_known), default=None))


def main():
    batch = collect(records(BATCH_CONTROL), "batch")
    pilot = collect(records(PILOT_CONTROL), "pilot")
    everything = batch + pilot
    result = dict(phase="p01_patrol (patrol intent)",
                  batch_runs=len(batch), pilot_runs=len(pilot), all_runs=len(everything),
                  channels={})
    for ch in CHANNELS:
        result["channels"][ch] = dict(
            batch=summarize(batch, ch), pilot=summarize(pilot, ch), all=summarize(everything, ch))
    # reconnaissance patrol-equivalent phase, reported separately for context
    recon = collect(records(BATCH_CONTROL), "batch-recon", phase="p01_observe", intent="reconnaissance")
    result["reconnaissance_p01_observe_batch_runs"] = len(recon)
    result["reconnaissance_channels"] = {ch: summarize(recon, ch) for ch in CHANNELS}
    out = ROOT / "tmp_v05/v05_final_20261004/ac4_patrol_d.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    print("written:", out)


if __name__ == "__main__":
    main()
