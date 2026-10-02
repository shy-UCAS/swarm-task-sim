"""C2: family_id 构造方式、family_namespace 哈希内容、template_spec 敏感性、split 一致性"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from swarm_sim.generation import GENERATOR_VERSION, canonical_hash, generate, _profile
from swarm_sim.dataset import family_split

PROFILE = ROOT / "generation_profiles/recon_pilot_v03.json"
TMP = ROOT / "audit_v04/tmp"
TMP.mkdir(parents=True, exist_ok=True)

# ---------- 1. 复现 family_namespace / base_id 构造 ----------
prof = _profile(PROFILE)
EXCLUDED = ("base_scene_count", "max_candidates_per_base", "variant_speed_factors")
print("=" * 100)
print("1) family_namespace 哈希包含的 profile 字段")
print("=" * 100)
print("profile 顶层键 (经 _profile 处理后): %s" % sorted(prof))
print("被排除的键: %s" % list(EXCLUDED))
included = sorted(k for k in prof if k not in EXCLUDED)
print("被包含的键 (%d): %s" % (len(included), included))
print()
print("template 字段处理: _profile 中 data.pop('template') 后写入 data['template_spec']")
print("  -> profile 中存在 'template' ? %s" % ("template" in prof))
print("  -> profile 中存在 'template_spec' ? %s" % ("template_spec" in prof))
print("  -> 因此 **template_spec 的全部内容被计入 family_namespace**")

ns = canonical_hash({k: v for k, v in prof.items() if k not in EXCLUDED})
print()
print("family_namespace = %s" % ns)
for bi in (0, 1, 2):
    bid = canonical_hash([GENERATOR_VERSION, ns, prof["master_seed"], bi])[:20]
    print("  base_index=%d -> base_id=%s -> family_id=recon_%s" % (bi, bid, bid))

# ---------- 2. 只改 template_spec 中一个字段, 比较 family_id ----------
print()
print("=" * 100)
print("2) 干跑: 同一 master_seed / base_index, 仅改 template_spec 一个字段")
print("=" * 100)


def run_variant(tag, mutate):
    variant = copy.deepcopy(prof)
    variant.pop("template", None)
    mutate(variant["template_spec"])
    out = TMP / ("c2_" + tag)
    if out.exists():
        import shutil
        shutil.rmtree(out)
    res = generate(variant, out)
    ml = json.loads((out / "mission_list.json").read_text(encoding="utf-8"))
    mf = json.loads((out / "generation_manifest.json").read_text(encoding="utf-8"))
    ns_v = canonical_hash({k: v for k, v in variant.items() if k not in EXCLUDED})
    return dict(tag=tag, ns=ns_v, family=ml["missions"][0]["family_id"],
                base_id=mf["bases"][0]["base_scene_id"],
                accepted_bases=mf["counts"]["accepted_bases"], counts=mf["counts"])


base = run_variant("orig", lambda t: None)
print("原始 template_spec:")
print("  family_namespace = %s" % base["ns"])
print("  family_id        = %s" % base["family"])

variants = [
    ("tracking_margin", lambda t: t["planner"].update(tracking_margin_m=2.0)),
    ("grid_m", lambda t: t["mission"]["observation_model"].update(grid_m=2.0)),
    ("platform_max_path", lambda t: t["platform"].update(max_path_length_m=2000.0)),
]
print()
for tag, mut in variants:
    v = run_variant(tag, mut)
    same_ns = v["ns"] == base["ns"]
    same_fam = v["family"] == base["family"]
    print("变体 %-18s family_namespace 相同? %-5s  family_id 相同? %-5s  (%s -> %s)"
          % (tag, same_ns, same_fam, base["family"], v["family"]))

# ---------- 3. recon_<id> vs patrol_<id> 的 split 一致性 ----------
print()
print("=" * 100)
print("3) family_split: 同一 base_id 的 recon_<id> 与 patrol_<id> 是否落入同一 split")
print("=" * 100)
gen = json.loads((ROOT / "generated/recon_pilot_v03_20260930/generation_manifest.json").read_text(encoding="utf-8"))
base_ids = [b["base_scene_id"] for b in gen["bases"]]
print("使用已生成 bundle 中的 %d 个 base_id" % len(base_ids))

agree = sum(family_split("recon_" + b) == family_split("patrol_" + b) for b in base_ids)
print("  实测: 同一 split 的比例 = %d/%d = %.4f" % (agree, len(base_ids), agree / len(base_ids)))

import heapq
import hashlib
rng_ids = [hashlib.sha256(str(i).encode()).hexdigest()[:20] for i in range(100)]
agree2 = sum(family_split("recon_" + b) == family_split("patrol_" + b) for b in rng_ids)
print("  对照(100 个 SHA256 前缀 id): %d/100 = %.4f" % (agree2, agree2 / 100))

# 理论期望: 三个 split 占比 70/15/15 -> 一致性概率 = .70^2 + .15^2 + .15^2 = 0.5350
print("  理论期望(若哈希均匀, 70/15/15): 0.70^2 + 0.15^2 + 0.15^2 = %.4f" % (0.70**2 + 0.15**2 + 0.15**2))

# 前缀长度敏感性: family 字符串前 5 字符相同, 仅前缀不同
for pref in ("recon", "patrolx"):
    pass
same_prefix = sum(family_split("recon_" + b) == family_split("patrol_" + b) for b in rng_ids)
print()
print("说明: family 字符串仅前缀不同(4-6 字符), 其余 20 位十六进制相同;")
print("      SHA256 对单字符改动即为雪崩, 因此两个 family 的 split 近似独立。")

json.dump(dict(base_family=base, variants=[dict(tag=t) for t, _ in variants],
               split_agree=agree, split_total=len(base_ids),
               split_agree_control=agree2),
          open(ROOT / "audit_v04/C2_family.json", "w"), indent=2, ensure_ascii=False)
