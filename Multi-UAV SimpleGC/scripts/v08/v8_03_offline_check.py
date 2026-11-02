"""V8-03 离线核对：清单与开发场景集、成员动力学独立、出发平移。

只读 SwarmData\\v07_first_edition 下的已有记录，只用标准库和 NumPy，不导入任何冻结模块。

用法:
    python -B v8_03_offline_check.py --stage inventory|quick|full|diag --data-root <数据根> --out <输出目录>

diag 为补充诊断（不在指令规格内）：对全量样本把窗口内误差按释放前后分段，只报告。

退出码: 0 = 完成且未触发停止条件; 2 = 触发停止条件（详见输出文件）; 1 = 参数或环境错误。
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sys
import time

import numpy as np

STEP_US = 100000
FIRST_EDITION = "v07_first_edition"
RUN_IDS = [
    "pilot_f000_005", "pilot_f005_020d", "prod_f020_060", "prod_f060_100", "prod_f100_140",
    "prod_f140_180", "prod_f180_220", "prod_f220_260", "prod_f260_300",
]
INTENTS = ["transit", "reconnaissance", "monitoring", "feint", "penetration"]
MODES = ["synchronous", "sequential"]
SPLITS = ["train", "val", "test"]
DEVSET_K = 40
PER_STRATUM = 20
THRESHOLD_M = 0.05
CROSS_TOL_M = 1e-9

# ---- 指令给出的预期值（第 4.3 节、附录 A/B） ----
EXPECTED_COUNTS = {
    "families": {"total": 300, "train": 222, "val": 36, "test": 42},
    "families_with_retained": {"total": 256, "train": 192, "val": 31, "test": 33},
    "retained_draws": {"total": 417, "train": 310, "val": 51, "test": 56},
    "retained_samples": {"total": 4170, "train": 3100, "val": 510, "test": 560},
}
EXPECTED_TRAIN_CELL = 310
EXPECTED_DEVSET_SHA = "f773cdf1ccea88c98bc064c2b8c6d12aa70b5cb93e25cb468629472bfa98dc52"
EXPECTED_FULL_SHA = "6f05e38ee49e14ddeb9cf4917569b0cd934be6ca42b18135ea4aa7b9667af16a"
EXPECTED_QUICK_SHA = "37c0318a6a851773f10653500205f8b5fe0fe5cb6aec7a47e129739ee14d43c6"
EXPECTED_FULL_MEMBERS = 1440
EXPECTED_DEVSET = [
    "family_s15_9b1a9f5a704a5a43", "family_s15_af5d80bd4e407c2e", "family_s15_232aa66e0775f46f",
    "family_s15_a4e519a7d128f6d1", "family_s15_fac1d381571b4d36", "family_s15_2a7eced81da133ad",
    "family_s15_c6b49487cb7c7e1f", "family_s15_b0c036776dcaff71", "family_s15_eeb311862e8c34e5",
    "family_s15_ad93040ec301fb17", "family_s15_12b1ed81bd5cde72", "family_s15_5ac40c0c4c1a9d0b",
    "family_s15_90108df3163855bf", "family_s15_2b42f691a28b01db", "family_s15_83cd2b234daaf514",
    "family_s15_3e9757b719a15bc8", "family_s15_54357502e6e9ebf2", "family_s15_353b8b5f4cae79d3",
    "family_s15_5e3f558bb4ffa439", "family_s15_505f19e9a810d7df", "family_s15_412545cc24001f48",
    "family_s15_f2ffae8f6cacb1fa", "family_s15_f2adfbfae12fbbad", "family_s15_291e9f1d18c41e22",
    "family_s15_9c5b7dee6d24ecb5", "family_s15_8c5b43031fc91ff5", "family_s15_6af8e2b8ab8f838d",
    "family_s15_84213fbe5aa46dcf", "family_s15_fae0e206a5549367", "family_s15_aaf17ad0eb548fd6",
    "family_s15_b94b354aeae617ba", "family_s15_340f1bccba15abf1", "family_s15_16b7eb91a4d4194d",
    "family_s15_3968861533cf6dd7", "family_s15_cfe0ba1515187f04", "family_s15_7b58eec82f695da3",
    "family_s15_da9847cb8fc64ef7", "family_s15_5efc7cddb20f4e95", "family_s15_f50ccf9d65d685fd",
    "family_s15_ebb78827c10a8498",
]
# (episode_id, run_id, 机数)
EXPECTED_QUICK = [
    ("family_s15_1547cdeafffd4a5a_ext_005_regular_synchronous", "prod_f260_300", 6),
    ("family_s15_15a8e07a0c733889_ext_005_regular_sequential", "prod_f020_060", 5),
    ("family_s15_aa4c66be8e85d64d_ext_001_regular_synchronous", "pilot_f005_020d", 9),
    ("family_s15_f50ccf9d65d685fd_ext_001_regular_sequential", "prod_f140_180", 6),
    ("family_s15_70443074d8bb2943_ext_007_regular_synchronous", "prod_f020_060", 7),
    ("family_s15_d997e815858f1b19_ext_002_regular_sequential", "prod_f100_140", 5),
    ("family_s15_40f2a315fe462d42_ext_003_regular_synchronous", "prod_f180_220", 8),
    ("family_s15_617b861a82b92aa4_ext_003_regular_sequential", "prod_f060_100", 8),
    ("family_s15_7b58eec82f695da3_ext_004_regular_synchronous", "prod_f140_180", 9),
    ("family_s15_27f705bbf706429a_ext_004_regular_sequential", "prod_f260_300", 12),
]


# ---------------------------------------------------------------- 第 3 节函数

def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def family_split_u(family_id):
    return int(_sha(f"traj2language-v07-fe-split-v1:{family_id}")[:8], 16) / 2**32


def family_split(family_id: str) -> str:
    u = family_split_u(family_id)
    if u < 0.70:
        return "train"
    if u < 0.85:
        return "val"
    return "test"


def devset_order_key(family_id: str) -> str:
    return _sha(f"traj2language-v08-devset-v1:{family_id}")


def select_devset(train_family_ids, k=40):
    ids = list(train_family_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("train_family_ids 含重复 ID")
    if len(ids) < k:
        raise ValueError(f"候选数 {len(ids)} 少于 k={k}")
    return sorted(ids, key=devset_order_key)[:k]


def sample_key(episode_id: str) -> str:
    return _sha(f"traj2language-v08-V8-03-sample:{episode_id}")


def _check_time_axis(t, name):
    t = np.asarray(t)
    if t.ndim != 1 or t.size == 0:
        raise ValueError(f"{name} 必须是非空一维数组")
    if int(t[0]) != 0:
        raise ValueError(f"{name} 不从 0 开始")
    if t.size > 1 and not np.all(np.diff(t.astype(np.int64)) == STEP_US):
        raise ValueError(f"{name} 相邻差不全为 {STEP_US} 微秒")
    return t.astype(np.int64)


def compare_member(joint_t_us, joint_p, joint_v, solo_t_us, solo_p, solo_v, delay_s):
    jt = _check_time_axis(joint_t_us, "joint_t_us")
    st = _check_time_axis(solo_t_us, "solo_t_us")
    jp = np.asarray(joint_p, dtype=float)
    jv = np.asarray(joint_v, dtype=float)
    sp = np.asarray(solo_p, dtype=float)
    sv = np.asarray(solo_v, dtype=float)
    if jp.shape != (jt.size, 3) or jv.shape != (jt.size, 3):
        raise ValueError("joint_p/joint_v 形状与 joint_t_us 不符")
    if sp.shape != (st.size, 3) or sv.shape != (st.size, 3):
        raise ValueError("solo_p/solo_v 形状与 solo_t_us 不符")
    delay_s = float(delay_s)
    if not math.isfinite(delay_s) or delay_s < 0.0:
        raise ValueError(f"delay_s 无效: {delay_s}")
    if abs(delay_s * 10.0 - round(delay_s * 10.0)) > 1e-7:
        raise ValueError(f"delay_s 不在 10 Hz 网格上: {delay_s}")
    shift_us = int(round(delay_s * 10.0)) * STEP_US

    in_win = jt <= st[-1] + shift_us
    n_in = int(in_win.sum())
    idx = np.maximum(0, (jt[in_win] - shift_us) // STEP_US)
    pos_err = float(np.linalg.norm(jp[in_win] - sp[idx], axis=1).max()) if n_in else None
    vel_err = float(np.linalg.norm(jv[in_win] - sv[idx], axis=1).max()) if n_in else None
    n_post = int(jt.size - n_in)
    post_disp = float(np.linalg.norm(jp[~in_win] - sp[-1], axis=1).max()) if n_post else None
    full = max(x for x in (pos_err, post_disp) if x is not None) if (n_in or n_post) else None
    return {
        "in_window_frames": n_in,
        "pos_err_max_m": pos_err,
        "vel_err_max_m_s": vel_err,
        "post_end_frames": n_post,
        "post_end_disp_max_m": post_disp,
        "full_pos_err_max_m": full,
    }


DIAG_EARLY_S = 10.0


def diag_member(joint_t_us, joint_p, joint_v, solo_t_us, solo_p, solo_v, delay_s):
    """补充诊断（不属于第 3 节规格）：把窗口内位置误差按释放前 / 释放后 10 s 内 / 其余分段。"""
    jt = _check_time_axis(joint_t_us, "joint_t_us")
    st = _check_time_axis(solo_t_us, "solo_t_us")
    jp = np.asarray(joint_p, dtype=float)
    sp = np.asarray(solo_p, dtype=float)
    shift_us = int(round(float(delay_s) * 10.0)) * STEP_US
    in_win = jt <= st[-1] + shift_us
    t = jt[in_win]
    idx = np.maximum(0, (t - shift_us) // STEP_US)
    e = np.linalg.norm(jp[in_win] - sp[idx], axis=1)
    pre = t < shift_us
    early = (t >= shift_us) & (t < shift_us + int(DIAG_EARLY_S * 1e6))
    late = t >= shift_us + int(DIAG_EARLY_S * 1e6)

    def seg_max(mask):
        return float(e[mask].max()) if mask.any() else None

    k = int(e.argmax())
    return {
        "pre_release_err_max_m": seg_max(pre),
        "release_10s_err_max_m": seg_max(early),
        "after_10s_err_max_m": seg_max(late),
        "argmax_offset_from_release_s": (int(t[k]) - shift_us) / 1e6,
        "argmax_offset_from_window_end_s": (int(t[k]) - int(t[-1])) / 1e6,
        "frames_over_threshold": int((e > THRESHOLD_M).sum()),
        "joint_speed_t0_m_s": float(np.linalg.norm(np.asarray(joint_v, dtype=float)[0])),
        "solo_speed_t0_m_s": float(np.linalg.norm(np.asarray(solo_v, dtype=float)[0])),
    }


# ---------------------------------------------------------------- 输出工具

def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, sort_keys=True, indent=1, ensure_ascii=False)
        f.write("\n")


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if r[h] is None else (repr(r[h]) if isinstance(r[h], float) else r[h])
                        for h in header])


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_after_swarmdata(directory):
    parts = [p for p in directory.replace("\\", "/").split("/") if p]
    lower = [p.lower() for p in parts]
    if "swarmdata" in lower:
        i = len(lower) - 1 - lower[::-1].index("swarmdata")
        parts = parts[i + 1:]
    return "/".join(parts)


def pct(values, q):
    return float(np.percentile(np.asarray(values, dtype=float), q)) if len(values) else None


# ---------------------------------------------------------------- 第 4 节：清单

def build_inventory(data_root):
    fe = os.path.join(data_root, FIRST_EDITION)
    family_runs = {}         # family_id -> set(run_id)
    draw_status = {}         # draw_key -> status
    draw_dupes = []
    reg_rows = {}            # (run_id, family_id) -> row
    descriptors = []         # (run_id, descriptor)
    for run_id in RUN_IDS:
        base = os.path.join(fe, run_id)
        man = load_json(os.path.join(base, "manifest.json"))
        for d in man["draws"]:
            if d["draw_key"] in draw_status:
                draw_dupes.append(d["draw_key"])
            draw_status[d["draw_key"]] = d["status"]
        desc = load_json(os.path.join(base, "descriptors", "descriptors.json"))
        if not isinstance(desc, list):
            raise ValueError(f"{run_id}/descriptors/descriptors.json 不是列表")
        for x in desc:
            descriptors.append((run_id, x))
            family_runs.setdefault(x["family_id"], set()).add(run_id)
        reg = load_json(os.path.join(base, "registration.json"))
        for row in reg["family_rows"]:
            reg_rows[(run_id, row["family_id"])] = row

    multi_batch = {f: sorted(r) for f, r in family_runs.items() if len(r) > 1}
    family_run = {f: sorted(r)[0] for f, r in family_runs.items()}

    retained_draws = {}      # family_id -> set(draw_key)
    samples = []
    for run_id, x in descriptors:
        fid = x["family_id"]
        dk = f"{fid}:{x['common_draw']['slot']}"
        if draw_status.get(dk) != "RETAINED":
            continue
        retained_draws.setdefault(fid, set()).add(dk)
        for mode in MODES:
            ep = f"{x['skeleton_id']}_{mode}"
            samples.append({
                "run_id": run_id, "skeleton_id": x["skeleton_id"], "family_id": fid,
                "intent": x["base_intent"], "mode": mode, "episode_id": ep,
                "agent_ids": list(x["agent_ids"]), "split": family_split(fid),
            })
    return {
        "family_run": family_run, "multi_batch": multi_batch, "draw_dupes": sorted(set(draw_dupes)),
        "retained_draws": retained_draws, "samples": samples, "reg_rows": reg_rows,
    }


def count_inventory(inv):
    fams = inv["family_run"]
    split_of = {f: family_split(f) for f in fams}

    def by_split(items):
        c = {"total": 0, "train": 0, "val": 0, "test": 0}
        for s in items:
            c["total"] += 1
            c[s] += 1
        return c

    counts = {
        "families": by_split(split_of[f] for f in fams),
        "families_with_retained": by_split(split_of[f] for f in inv["retained_draws"]),
        "retained_draws": by_split(split_of[f] for f, ks in inv["retained_draws"].items() for _ in ks),
        "retained_samples": by_split(s["split"] for s in inv["samples"]),
    }
    cells = {f"{i}|{m}": 0 for i in INTENTS for m in MODES}
    other = {}
    for s in inv["samples"]:
        if s["split"] != "train":
            continue
        key = f"{s['intent']}|{s['mode']}"
        if key in cells:
            cells[key] += 1
        else:
            other[key] = other.get(key, 0) + 1
    return counts, cells, other


def select_samples(inv):
    train = [s for s in inv["samples"] if s["split"] == "train"]
    full = []
    for intent in INTENTS:
        for mode in MODES:
            layer = sorted((s for s in train if s["intent"] == intent and s["mode"] == mode),
                           key=lambda s: sample_key(s["episode_id"]))
            full.extend(layer[:PER_STRATUM])
    quick = [full[i * PER_STRATUM] for i in range(len(INTENTS) * len(MODES))
             if i * PER_STRATUM < len(full)]
    return full, quick


def ids_sha(ids):
    return _sha("\n".join(ids))


def check_inventory(inv):
    """返回 (summary, devset_ids, full, quick, stop_reasons)。"""
    counts, cells, other = count_inventory(inv)
    stop = []
    counts_match = counts == EXPECTED_COUNTS
    cells_match = all(v == EXPECTED_TRAIN_CELL for v in cells.values()) and not other
    if not counts_match:
        stop.append("第 4.3 节计数与预期不一致")
    if not cells_match:
        stop.append("train 保留样本 base_intent×mode 各格不全为 310")
    if inv["multi_batch"]:
        stop.append("有场景族出现在多个批次的描述中")
    if inv["draw_dupes"]:
        stop.append("manifest 中有重复的 draw_key")

    candidates = sorted(f for f in inv["retained_draws"] if family_split(f) == "train")
    devset = select_devset(candidates, k=DEVSET_K)
    devset_sha = ids_sha(devset)
    if devset_sha != EXPECTED_DEVSET_SHA or devset != EXPECTED_DEVSET:
        stop.append("开发场景集与附录 A 不一致")

    full, quick = select_samples(inv)
    full_sha = ids_sha([s["episode_id"] for s in full])
    quick_sha = ids_sha([s["episode_id"] for s in quick])
    if full_sha != EXPECTED_FULL_SHA:
        stop.append("全量抽样清单 SHA256 与预期不一致")
    if quick_sha != EXPECTED_QUICK_SHA:
        stop.append("快速抽样清单 SHA256 与预期不一致")
    quick_vs_b = [{"position": i + 1, "actual": (s["episode_id"], s["run_id"], len(s["agent_ids"])),
                   "expected": e}
                  for i, (s, e) in enumerate(zip(quick, EXPECTED_QUICK))
                  if (s["episode_id"], s["run_id"], len(s["agent_ids"])) != e]
    if quick_vs_b or len(quick) != len(EXPECTED_QUICK):
        stop.append("快速清单与附录 B 不一致")

    summary = {
        "counts_actual": counts,
        "counts_expected": EXPECTED_COUNTS,
        "counts_match": counts_match,
        "train_intent_mode_cells_actual": cells,
        "train_intent_mode_cells_unexpected_keys": other,
        "train_intent_mode_cells_expected_each": EXPECTED_TRAIN_CELL,
        "train_intent_mode_cells_match": cells_match,
        "families_in_multiple_batches": inv["multi_batch"],
        "duplicate_draw_keys": inv["draw_dupes"],
        "devset_candidates": len(candidates),
        "devset_ids_sha256": {"actual": devset_sha, "expected": EXPECTED_DEVSET_SHA,
                              "match": devset_sha == EXPECTED_DEVSET_SHA},
        "devset_positions_differing_from_appendix_a": [
            {"order": i + 1, "actual": a, "expected": b}
            for i, (a, b) in enumerate(zip(devset, EXPECTED_DEVSET)) if a != b],
        "full_sample_sha256": {"actual": full_sha, "expected": EXPECTED_FULL_SHA,
                               "match": full_sha == EXPECTED_FULL_SHA},
        "quick_sample_sha256": {"actual": quick_sha, "expected": EXPECTED_QUICK_SHA,
                                "match": quick_sha == EXPECTED_QUICK_SHA},
        "quick_differing_from_appendix_b": quick_vs_b,
        "full_sample_count": len(full),
        "full_sample_member_count": sum(len(s["agent_ids"]) for s in full),
        "full_sample_member_count_expected": EXPECTED_FULL_MEMBERS,
    }
    return summary, devset, full, quick, stop


def vehicle_bin(n):
    if n <= 5:
        return "4-5" if n >= 4 else f"<=3({n})"
    if n <= 8:
        return "6-8"
    if n <= 11:
        return "9-11"
    return ">=12"


def distribution(rows):
    out = {"layout": {}, "facility_count": {}, "vehicle_count": {}, "vehicle_count_bin": {}}
    for r in rows:
        for k, v in (("layout", r["layout"]), ("facility_count", str(r["facility_count"])),
                     ("vehicle_count", str(r["vehicle_count"])),
                     ("vehicle_count_bin", vehicle_bin(int(r["vehicle_count"])))):
            out[k][v] = out[k].get(v, 0) + 1
    return out


def stage_inventory(data_root, out):
    inv = build_inventory(data_root)
    summary, devset, full, quick, stop = check_inventory(inv)

    fam_rows = []
    for f in sorted(inv["family_run"]):
        fam_rows.append({"family_id": f, "run_id": inv["family_run"][f], "split": family_split(f),
                         "split_u": family_split_u(f),
                         "retained_draws": len(inv["retained_draws"].get(f, ()))})
    write_csv(os.path.join(out, "families.csv"),
              ["family_id", "run_id", "split", "split_u", "retained_draws"], fam_rows)

    dev_rows, missing, mismatched, no_reg = [], [], [], []
    for order, f in enumerate(devset, 1):
        run_id = inv["family_run"][f]
        row = inv["reg_rows"].get((run_id, f))
        if row is None:
            no_reg.append(f)
            row = {}
        rel = rel_after_swarmdata(row.get("directory", ""))
        reg_sha = row.get("sha256", {})
        verified = bool(row)
        for name in ("public_scene.json", "family_initial.json"):
            p = os.path.join(data_root, *rel.split("/"), name)
            if not os.path.isfile(p):
                missing.append(f"{rel}/{name}")
                verified = False
                continue
            actual = file_sha256(p)
            if actual != reg_sha.get(name):
                mismatched.append({"file": f"{rel}/{name}", "actual": actual,
                                   "registered": reg_sha.get(name)})
                verified = False
        dev_rows.append({
            "order": order, "family_id": f, "order_key": devset_order_key(f), "run_id": run_id,
            "directory_rel": rel, "public_scene_sha256": reg_sha.get("public_scene.json"),
            "family_initial_sha256": reg_sha.get("family_initial.json"),
            "scene_files_verified": verified, "layout": row.get("layout"),
            "vehicle_count": row.get("vehicle_count"), "facility_count": row.get("facility_count"),
            "map_side_m": row.get("map_side_m"),
        })
    if mismatched:
        stop.append("开发场景集场景文件 SHA256 与登记值不同")
    dev_fields = ["order", "family_id", "order_key", "run_id", "directory_rel", "public_scene_sha256",
                  "family_initial_sha256", "scene_files_verified", "layout", "vehicle_count",
                  "facility_count", "map_side_m"]
    write_json(os.path.join(out, "devset_v08.json"), dev_rows)
    write_csv(os.path.join(out, "devset_v08.csv"), dev_fields, dev_rows)

    cand_rows = []
    for f in sorted(f for f in inv["retained_draws"] if family_split(f) == "train"):
        row = inv["reg_rows"].get((inv["family_run"][f], f))
        if row is not None:
            cand_rows.append(row)
    summary["devset_scene_files"] = {
        "verified": sum(r["scene_files_verified"] for r in dev_rows), "total": len(dev_rows),
        "missing_files": missing, "sha256_mismatch": mismatched, "no_registration_row": no_reg,
    }
    summary["devset_diagnostics"] = {
        "devset_40": distribution([r for r in dev_rows if r["layout"] is not None]),
        "candidates_192": distribution(cand_rows),
        "candidates_with_registration_row": len(cand_rows),
        "vehicle_count_bins": "4-5 / 6-8 / 9-11 / >=12",
    }

    write_json(os.path.join(out, "sample_episodes.json"), [
        {"order": i + 1, "intent": s["intent"], "mode": s["mode"], "run_id": s["run_id"],
         "skeleton_id": s["skeleton_id"], "episode_id": s["episode_id"],
         "sample_key": sample_key(s["episode_id"])} for i, s in enumerate(full)])
    summary["stop_conditions_triggered"] = stop
    summary["all_match"] = not stop
    write_json(os.path.join(out, "inventory_summary.json"), summary)
    return stop


# ---------------------------------------------------------------- 第 5 节：动力学核对

def process_sample(data_root, s, with_diag=False):
    """返回 (members, sample_record)。sample_record['problem'] 非空时样本未参与比较。"""
    rel_r = f"{FIRST_EDITION}/{s['run_id']}/episodes/{s['skeleton_id']}"
    R = os.path.join(data_root, *rel_r.split("/"))
    M = os.path.join(R, s["mode"])
    rec = {"episode_id": s["episode_id"], "intent": s["intent"], "mode": s["mode"],
           "run_id": s["run_id"], "problem": None, "detail": None}
    try:
        tc = load_json(os.path.join(R, "timing_calibration.json"))
        rnd = int(tc["calibration_round"])
        gdir = f"geometry_{rnd - 1:02d}"
        G = os.path.join(R, gdir)
        rec["geometry_dir"] = gdir
        sk_r = file_sha256(os.path.join(R, "skeleton.json"))
        sk_g = file_sha256(os.path.join(G, "skeleton.json"))
        if sk_r != sk_g:
            rec["problem"] = "source_mismatch"
            rec["detail"] = {"skeleton_sha256_R": sk_r, "skeleton_sha256_G": sk_g}
            return [], rec
        with np.load(os.path.join(M, "truth_10hz.npz"), allow_pickle=False) as z:
            jt = z["time_us"]
            jp = z["p"]
            jv = z["v"]
            jids = [str(a) for a in z["agent_ids"]]
        delays = load_json(os.path.join(M, "source.json"))["departure_delays_s"]
        recorded = float(load_json(os.path.join(M, "solo_overlay_comparison.json"))["position_error_max_m"])
    except FileNotFoundError as e:
        rec["problem"] = "file_missing"
        rec["detail"] = os.path.relpath(e.filename, data_root).replace("\\", "/") if e.filename else str(e)
        return [], rec
    except Exception as e:  # noqa: BLE001 - 读取失败一律记录后继续
        rec["problem"] = "read_failure"
        rec["detail"] = f"{type(e).__name__}: {e}"
        return [], rec

    rec["n_agents"] = len(jids)
    rec["agent_ids_match_descriptor"] = sorted(jids) == sorted(s["agent_ids"])
    rec["agent_ids_match_delays"] = sorted(jids) == sorted(delays)
    members = []
    try:
        for col, a in enumerate(jids):
            sp_path = os.path.join(G, f"single_agent_{a}.npz")
            with np.load(sp_path, allow_pickle=False) as z:
                st = z["time_us"]
                sp = z["p"][:, 0, :]
                sv = z["v"][:, 0, :]
                sids = [str(x) for x in z["agent_ids"]]
                status = str(z["execution_status"])
            if sids != [a]:
                raise ValueError(f"{gdir}/single_agent_{a}.npz agent_ids={sids}")
            d = float(delays[a])
            r = compare_member(jt, jp[:, col, :], jv[:, col, :], st, sp, sv, d)
            if with_diag:
                r.update(diag_member(jt, jp[:, col, :], jv[:, col, :], st, sp, sv, d))
            members.append({"episode_id": s["episode_id"], "intent": s["intent"], "mode": s["mode"],
                            "agent_id": a, "delay_s": d, "solo_status": status, **r})
    except FileNotFoundError as e:
        rec["problem"] = "file_missing"
        rec["detail"] = os.path.relpath(e.filename, data_root).replace("\\", "/") if e.filename else str(e)
        return [], rec
    except Exception as e:  # noqa: BLE001
        rec["problem"] = "read_failure"
        rec["detail"] = f"{type(e).__name__}: {e}"
        return [], rec

    mine = max(m["full_pos_err_max_m"] for m in members)
    rec["recorded_position_error_max_m"] = recorded
    rec["members_full_pos_err_max_m"] = mine
    rec["cross_check_abs_diff_m"] = abs(mine - recorded)
    rec["cross_check_pass"] = abs(mine - recorded) <= CROSS_TOL_M
    return members, rec


def judgement(members, pick):
    sel = [m for m in members if pick(m)]
    if not sel:
        return {"members": 0, "pos_err_max_m": None, "worst": None, "threshold_m": THRESHOLD_M,
                "pass": None, "note": "无参与成员，无法判定"}
    w = max(sel, key=lambda m: m["pos_err_max_m"])
    return {"members": len(sel), "pos_err_max_m": w["pos_err_max_m"], "threshold_m": THRESHOLD_M,
            "worst": {"episode_id": w["episode_id"], "agent_id": w["agent_id"], "delay_s": w["delay_s"]},
            "pass": w["pos_err_max_m"] <= THRESHOLD_M}


def summarize(members, recs, expected_samples):
    ok = [r for r in recs if r["problem"] is None]
    errs = [m["pos_err_max_m"] for m in members]
    delays = [m["delay_s"] for m in members]
    pos_delays = [d for d in delays if d > 0]
    post = [m for m in members if m["post_end_frames"] > 0]
    status_counts = {}
    for m in members:
        status_counts[m["solo_status"]] = status_counts.get(m["solo_status"], 0) + 1
    strata = {}
    for intent in INTENTS:
        for mode in MODES:
            e = [m["pos_err_max_m"] for m in members if m["intent"] == intent and m["mode"] == mode]
            strata[f"{intent}|{mode}"] = {
                "members": len(e), "pos_err_max_m_max": max(e) if e else None,
                "pos_err_max_m_median": float(np.median(e)) if e else None}
    j2_sel = sorted((m for m in members if m["delay_s"] > 0),
                    key=lambda m: (-m["pos_err_max_m"], m["episode_id"], m["agent_id"]))
    cross_fail = [{"episode_id": r["episode_id"], "abs_diff_m": r["cross_check_abs_diff_m"],
                   "recorded_m": r["recorded_position_error_max_m"],
                   "computed_m": r["members_full_pos_err_max_m"]}
                  for r in ok if not r["cross_check_pass"]]
    return {
        "samples_expected": expected_samples,
        "samples_compared": len(ok),
        "members_compared": len(members),
        "percentile_method": "numpy.percentile linear",
        "judgement_1_zero_delay": judgement(members, lambda m: m["delay_s"] == 0.0),
        "judgement_2_positive_delay": judgement(members, lambda m: m["delay_s"] > 0.0),
        "judgement_2_detail": {
            "pos_err_max_m_percentiles": {str(q): pct([m["pos_err_max_m"] for m in j2_sel], q)
                                          for q in (50, 90, 95, 99)},
            "top20": [{k: m[k] for k in ("episode_id", "agent_id", "delay_s", "pos_err_max_m",
                                         "vel_err_max_m_s")} for m in j2_sel[:20]],
        },
        "all_members_pos_err_max_m": {"max": max(errs) if errs else None, "p50": pct(errs, 50),
                                      "p95": pct(errs, 95), "p99": pct(errs, 99)},
        "cross_check": {"tolerance_m": CROSS_TOL_M,
                        "pass_samples": sum(1 for r in ok if r["cross_check_pass"]),
                        "fail_samples": len(cross_fail), "failures": cross_fail,
                        "abs_diff_max_m": max((r["cross_check_abs_diff_m"] for r in ok), default=None)},
        "strata": strata,
        "velocity": {"vel_err_max_m_s_max": max((m["vel_err_max_m_s"] for m in members), default=None),
                     "vel_err_max_m_s_p95": pct([m["vel_err_max_m_s"] for m in members], 95)},
        "delay_coverage": {
            "zero_delay_members": len(delays) - len(pos_delays),
            "positive_delay_members": len(pos_delays),
            "max_s": max(delays) if delays else None,
            "all_members_percentiles_s": {str(q): pct(delays, q) for q in (50, 90, 99)},
            "positive_members_percentiles_s": {str(q): pct(pos_delays, q) for q in (50, 90, 99)},
        },
        "post_end_hold": {
            "members_with_post_end": len(post),
            "post_end_disp_max_m_max": max((m["post_end_disp_max_m"] for m in post), default=None),
            "post_end_disp_max_m_p95": pct([m["post_end_disp_max_m"] for m in post], 95),
            "post_end_frames_max": max((m["post_end_frames"] for m in post), default=0),
            "post_end_max_s": max((m["post_end_frames"] for m in post), default=0) * STEP_US / 1e6,
        },
        "solo_execution_status_counts": status_counts,
        "source_mismatch": [r for r in recs if r["problem"] == "source_mismatch"],
        "file_missing": [r for r in recs if r["problem"] == "file_missing"],
        "read_failure": [r for r in recs if r["problem"] == "read_failure"],
        "agent_id_inconsistencies": [r["episode_id"] for r in ok
                                     if not (r["agent_ids_match_descriptor"] and r["agent_ids_match_delays"])],
        "samples": recs,
    }


MEMBER_FIELDS = ["episode_id", "intent", "mode", "agent_id", "delay_s", "solo_status", "in_window_frames",
                 "pos_err_max_m", "vel_err_max_m_s", "post_end_frames", "post_end_disp_max_m",
                 "full_pos_err_max_m"]


def stage_dynamics(data_root, out, stage):
    inv = build_inventory(data_root)
    summary, _devset, full, quick, stop = check_inventory(inv)
    if stop:
        write_json(os.path.join(out, f"{stage}_inventory_stop.json"),
                   {"stop_conditions_triggered": stop, "inventory": summary})
        return stop
    samples = quick if stage == "quick" else full
    members, recs = [], []
    progress = os.path.join(out, "full_progress.txt") if stage == "full" else None
    t0 = time.time()
    for i, s in enumerate(samples, 1):
        ms, rec = process_sample(data_root, s)
        members.extend(ms)
        recs.append(rec)
        if progress and (i % 20 == 0 or i == len(samples)):
            with open(progress, "a", encoding="utf-8", newline="\n") as f:
                f.write(f"{i}/{len(samples)} samples, {len(members)} members, "
                        f"elapsed {time.time() - t0:.1f} s\n")
    res = summarize(members, recs, len(samples))
    if stage == "full":
        res["members_expected"] = EXPECTED_FULL_MEMBERS
    j1 = res["judgement_1_zero_delay"]["pass"]
    res["checkpoint"] = {
        "judgement_1_failed": j1 is False,
        "cross_check_failed": res["cross_check"]["fail_samples"] > 0,
    }
    write_json(os.path.join(out, f"{stage}_results.json"), res)
    write_csv(os.path.join(out, f"{stage}_members.csv"), MEMBER_FIELDS, members)
    halt = []
    if j1 is False:
        halt.append("判定一不通过")
    if res["cross_check"]["fail_samples"]:
        halt.append("交叉核对不一致")
    return halt


DIAG_FIELDS = ["episode_id", "intent", "mode", "agent_id", "delay_s", "pos_err_max_m",
               "pre_release_err_max_m", "release_10s_err_max_m", "after_10s_err_max_m",
               "argmax_offset_from_release_s", "argmax_offset_from_window_end_s",
               "frames_over_threshold", "joint_speed_t0_m_s", "solo_speed_t0_m_s"]
DIAG_SEGMENTS = ["pre_release_err_max_m", "release_10s_err_max_m", "after_10s_err_max_m"]


def stage_diag(data_root, out):
    """补充诊断：对全量 200 条样本把窗口内误差分段，只报告，不参与判定。"""
    inv = build_inventory(data_root)
    _summary, _devset, full, _quick, stop = check_inventory(inv)
    if stop:
        return stop
    members = []
    for s in full:
        ms, _rec = process_sample(data_root, s, with_diag=True)
        members.extend(ms)
    seg = {}
    for k in DIAG_SEGMENTS:
        vals = [m[k] for m in members if m[k] is not None]
        seg[k] = {"members_with_segment": len(vals), "max": max(vals, default=None),
                  "p50": pct(vals, 50), "p95": pct(vals, 95),
                  "members_over_threshold": sum(1 for v in vals if v > THRESHOLD_M)}
    over = [m for m in members if m["pos_err_max_m"] > THRESHOLD_M]
    where = {k: 0 for k in DIAG_SEGMENTS}
    for m in over:
        where[max(DIAG_SEGMENTS, key=lambda k: -1.0 if m[k] is None else m[k])] += 1
    late = sorted((m for m in members if (m["after_10s_err_max_m"] or 0.0) > THRESHOLD_M),
                  key=lambda m: (-m["after_10s_err_max_m"], m["episode_id"], m["agent_id"]))
    v0 = [m["joint_speed_t0_m_s"] for m in members]
    res = {
        "note": "补充诊断，不属于第 5.3 节判定；窗口与 compare_member 相同，分段按联合时刻相对释放时刻",
        "early_segment_s": DIAG_EARLY_S,
        "threshold_m": THRESHOLD_M,
        "members": len(members),
        "segments": seg,
        "members_over_threshold": len(over),
        "members_over_threshold_by_segment_of_max": where,
        "after_10s_over_threshold": [{k: m[k] for k in DIAG_FIELDS} for m in late],
        "joint_speed_t0_m_s": {"members_nonzero": sum(1 for v in v0 if v > 0.0),
                               "max": max(v0, default=None), "p50": pct(v0, 50)},
        "solo_speed_t0_equals_joint_speed_t0": sum(1 for m in members
                                                   if m["solo_speed_t0_m_s"] == m["joint_speed_t0_m_s"]),
    }
    write_json(os.path.join(out, "diag_results.json"), res)
    write_csv(os.path.join(out, "diag_members.csv"), DIAG_FIELDS, members)
    return []


# ---------------------------------------------------------------- 入口

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", required=True, choices=["inventory", "quick", "full", "diag"])
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    data_root = os.path.abspath(a.data_root)
    out = os.path.abspath(a.out)
    rel = os.path.relpath(out, data_root) if os.path.splitdrive(out)[0].lower() == \
        os.path.splitdrive(data_root)[0].lower() else ".."
    if not rel.startswith("..") and rel.split(os.sep)[0].startswith("v07_"):
        print(f"拒绝: 输出目录位于 SwarmData\\v07_* 内: {out}", file=sys.stderr)
        return 1
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    if a.stage == "inventory":
        stop = stage_inventory(data_root, out)
    elif a.stage == "diag":
        stop = stage_diag(data_root, out)
    else:
        stop = stage_dynamics(data_root, out, a.stage)
    write_json(os.path.join(out, f"timing_{a.stage}.json"),
               {"stage": a.stage, "elapsed_s": round(time.time() - t0, 1)})
    if stop:
        print("STOP: " + "; ".join(stop))
        return 2
    print(f"{a.stage}: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
