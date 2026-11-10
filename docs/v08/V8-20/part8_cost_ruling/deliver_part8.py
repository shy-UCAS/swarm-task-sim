"""Final immutable audit and review delivery, after all computation has ended."""
import datetime
import importlib.util
import shutil
import subprocess
import time
from evidence_utils import *

started = time.perf_counter()
external = ROOT / "delivery_cost_ruling_r1"
out = DOC / "part8_cost_ruling"
assert not external.exists() and not out.exists()
external.mkdir()
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
dump(external / "started.json", {"started_utc": start}, exclusive=True)
assert read(DOC / "part7_cost_ruling/checkpoint.json")["passed"]
job = {"phase": 8, "stage": "delivery_audit", "intent": "area_search", "round": "cost_ruling_r1",
       "workers": 1, "root_pid": os.getpid(), "status": "running", "started_utc": start}
dump(ROOT / "system_monitor/current_job.json", job)
changes = audit()
m = read(DOC / "manifest.json")
baseline_count = baseline_bytes = 0
for key, facts in read(ROOT / "snapshot/part1_r1/baseline_files.json").items():
    intent, cid = key.split("/")
    folder = Path(m["baselines"][intent]["path"]) / "contracts" / cid
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(facts):
        changes.append("baseline_file_set:" + key)
    for name, fact in facts.items():
        p = folder / name
        baseline_count += 1
        baseline_bytes += fact["bytes"]
        if sha(p) != fact["sha256"] or p.stat().st_mtime_ns != fact["mtime_ns"] or p.stat().st_size != fact["bytes"]:
            changes.append(str(p))


def git(*argv, cwd=REPO):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *argv], capture_output=True,
                            text=True, encoding="utf-8", check=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    return result.stdout.strip()


trees = {}
for name, expected in m["frozen_worktrees"].items():
    folder = BASE / name
    fact = {"head": git("rev-parse", "HEAD", cwd=folder), "status": git("status", "--short", cwd=folder)}
    trees[name] = fact
    if fact != expected:
        changes.append("frozen_worktree:" + name)
branch = git("branch", "--show-current")
assert branch == "review/v08/V8-20-area-search"
ancestor = subprocess.run(["git", "--no-optional-locks", "-C", str(REPO), "merge-base", "--is-ancestor", "7b942db", "HEAD"]).returncode
assert ancestor == 0
owners_tracked = git("ls-files", "--", "docs/v08/V8-17/owner_rerun.json", "docs/v08/V8-18/owner_rerun.json", "docs/v08/V8-19/owner_rerun.json")
assert not owners_tracked
assert not changes, changes
frozen = {"changes": changes, "whole_files": len(m["frozen_files"]), "symbols": len(m["frozen_symbols"]),
    "owner_files": len(m["owners"]), "input_files": len(read(ROOT / "snapshot/part1_r1/inputs.json")),
    "configs": len(read(DOC / "part3/final_audit.json")["supplemental_all_config_baseline_sha256"]),
    "baseline_contracts": len(read(ROOT / "snapshot/part1_r1/baseline_files.json")),
    "baseline_files": baseline_count, "baseline_bytes_hashed": baseline_bytes,
    "frozen_worktrees": trees, "branch": branch, "head_before_delivery_commit": git("rev-parse", "HEAD"),
    "continued_from_7b942db_without_reset": True, "owners_tracked": [],
    "dev_v08": git("rev-parse", "refs/heads/dev/v0.8"), "read_only_audit_wall_s": time.perf_counter() - started}
dump(external / "final_audit.json", frozen)

# Keep the independent monitor through the final read-only audit, then close it normally.
session = read(ROOT / "system_monitor/session.json")
monitor = Path(session["directory"])
(monitor / "stop.request").write_text("All authorized computation and final frozen audit ended.\n", encoding="utf-8")
last = None
for _ in range(30):
    with (monitor / "metrics.jsonl").open("rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 16384))
        try:
            last = json.loads(f.read().splitlines()[-1])
        except (ValueError, IndexError):
            last = None
    if last is not None and last.get("event") == "stopped":
        break
    time.sleep(.5)
assert last is not None and last.get("event") == "stopped", last
spec = importlib.util.spec_from_file_location("resource_summary", DOC / "analyze_resources.py")
resource = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resource)
resources = resource.summarize(monitor)
dump(external / "resources.json", resources)
dump(external / "monitor_evidence_index.json", index(monitor))
out.mkdir()
shutil.copyfile(external / "final_audit.json", out / "final_audit.json")
shutil.copyfile(external / "resources.json", out / "resources.json")
shutil.copyfile(external / "monitor_evidence_index.json", out / "monitor_evidence_index.json")
for name in ("evidence_utils.py", "deliver_part8.py"):
    shutil.copyfile(TASK / name, out / name)
part7 = read(DOC / "part7_cost_ruling/checkpoint.json")
part5 = read(DOC / "part5_cost_ruling/checkpoint.json")
full = read(ROOT / "full/area_cost_ruling_r1/summary.json")
stops = {"prewarm_wall_s": part5["prewarm"]["wall_s"], "prewarm_limit_s": 2700.,
    "skeleton_dispatch_wall_s": part5["skeleton"]["dispatch_wall_s"], "skeleton_limit_s": 1800.,
    "quick_cost_projection_s": read(ROOT / "cost_ruling_r1/sector_o34_d3/result.json")["projected_wall_s"],
    "reestimate_projection_s": read(ROOT / "smoke/prewarm_runtime_max_r1/result.json")["projection_s"],
    "projection_limit_s": 1800., "winning_split_depth_min_m": read(DOC / "part5_cost_ruling/distributions.json")["split_depths_winning_members_m"]["quantiles"]["min"],
    "cut_depth_failure_is_ordinary": True,
    "cut_depth_rejected_attempts": part5["skeleton"]["checkpoint"]["diagnostics"]["split_depth_rejected_attempts"],
    "all_failed_skeleton_attempts": part5["skeleton"]["checkpoint"]["diagnostics"]["failed_attempts"],
    "cut_depth_is_majority": part5["skeleton"]["checkpoint"]["diagnostics"]["split_depth_majority_of_failures"],
    "p0_violations": [], "old_intent_byte_gates": "200/200 equal; exclusions=[]",
    "serial_five": "5/5 equal; exclusions=[]"}
dump(out / "stop_values.json", stops)
commit_log = git("log", "--reverse", "--format=%H%x09%s", "fd27b9b..HEAD")
(out / "commit_history_before_delivery.txt").write_text(commit_log + "\n", encoding="utf-8", newline="\n")
elapsed = time.perf_counter() - started
checkpoint = {"part": 8, "passed": True, "audit": frozen, "stop_values": stops,
    "resources_stopped_normally": True, "delivery_elapsed_s_excluding_final_commit_push": elapsed,
    "started_utc": start, "final_push_receipt": str(external / "final_push.json"),
    "acceptance": "execution_complete_pending_planning_reviewer_independent_acceptance"}
dump(out / "checkpoint.json", checkpoint)
dump(external / "checkpoint.json", checkpoint)
a = read(DOC / "acceptance.json")
a["status"] = "execution_complete_pending_planning_reviewer_independent_acceptance"
a["part8_checkpoint"] = str(out / "checkpoint.json")
a["final_push_receipt"] = str(external / "final_push.json")
dump(DOC / "acceptance.json", a)
report = (DOC / "REPORT.md").read_text(encoding="utf-8")
old = "当前状态：从 7b942db 按成本裁定恢复，第 1、2 部分接受；新裁定修改独立提交 891b57c7a2aa7c65912bceeb2385e1434dbd6643。第 3、4 部分完成，第二轮五意图 100 合同字节门禁通过；正式预建与第 5 部分待执行，未获完整验收。此前停止与交付记录按发生时状态保留。"
assert old in report
report = report.replace(old, "当前状态：从 7b942db 连续执行，成本修改独立提交 891b57c7a2aa7c65912bceeb2385e1434dbd6643；第 1–8 部分执行检查已完成，原样数值/几何/产物预置全部通过。两轮五意图 200/200、五键复跑 5/5 完整字节一致；骨架与主批均 194/200、快批 20/20、多样性 99/100。最终研究接受待规划审查方独立复跑。下文早期停止与中间状态按发生时历史保留，最新交付以第 8 部分成本裁定轮为准。", 1)
report = report.replace("任何实际转弯切入点在 warning 内深度小于 10 m 即停止。", "附录原本规定深度不足 10 m 即停止；成本裁定 2.4 已将此改为普通 area_search_route 失败，先执行固定 head 放置序列、不换格重抽、计入 20 次预算；若占失败多数则带证据交审查。", 1)
report = report.replace("超过 a_hi 即不可行；取消分段代数求根及 numeric_unresolved 分支。", "成本裁定改为固定 a_out/a_hi 端点判定 c 可行，只对三层抽中的 c 执行此扫描；取消分段代数求根及 numeric_unresolved 分支。", 1)
report = report.replace("弦预建墙钟超过 2700 s 停；200 只骨架墙钟（不含预建）超过 1800 s 停；裁定 1 切入深度小于 10 m 停。", "弦集合加扇区表合并预建墙钟超过 2700 s 停；200 只骨架墙钟（不含预建）超过 1800 s 停；新裁定单查询按墙钟×151/24 外推超过 1800 s 停。切入深度不足 10 m 按成本裁定只拒绝该尝试。", 1)
report += "\n\n## 第 8 部分成本裁定轮：交付、首尾审计与资源归档\n\n"
report += "八部分按顺序分别提交；本轮从 7b942db 继续、没有重置。仅审查分支正常推送，无 main/强推/dev 合并。三份 owner 始终未跟踪且字节/mtime 不变，冻结工作树与数据仅读取。第 3 部分最初成本止损及失败回执保留，不能与本轮已通过产物混为一谈。\n\n"
report += "| 部分 | 最终执行结论 | 实测墙钟及范围 |\n|---|---|---|\n"
report += "| 1 | 登记/冻结/基线通过，沿用已接受结果 | 登记脚本 19.642261 s；开工到快照结束 208.137501 s |\n"
report += "| 2 | 第一轮 100/100 门禁通过，沿用已接受结果 | 阶段 3597.705079 s（含暂停/重启）；门禁 1568.569735 s |\n"
report += "| 3 | 成本新规则、真实 12 机、RNG/缓存通过 | 本次修改到证据 1496.011110 s；旧成本失败 2187.166112 s 单列历史 |\n"
report += "| 4 | 冻结核验/序列化/168 旧测试及第二轮门禁通过 | 开发及门禁 3248.014473 s；门禁 704.351408 s |\n"
report += f"| 5 | 固定 200 骨架 194 成功，检查点通过 | 合并预建 {stops['prewarm_wall_s']:.6f} s；骨架派发 {stops['skeleton_dispatch_wall_s']:.6f} s |\n"
report += "| 6 | 固定快批 20/20，磁盘复核与检查点通过 | 派发 74.814573 s；含复核 94.992606 s |\n"
report += f"| 7 | 主批 194/200、多样性 99/100；五键/原样产物预置/配对通过 | 总阶段 {part7['part7_elapsed_s']:.6f} s；full 含磁盘 {part7['full_wrapper_wall_s_including_disk_reverification']:.6f} s；serial5 {part7['serial_five_wall_s']:.6f} s；产物预置 {part7['artifact_preset_wall_s']:.6f} s |\n"
report += f"| 8 | 首尾审计通过、资源归档、审查交付 | 当前交付整理 {elapsed:.6f} s；含最终推送墙钟见外部 final_push.json |\n\n"
report += f"止损实测：合并预建 {stops['prewarm_wall_s']:.6f}/2700 s，骨架 {stops['skeleton_dispatch_wall_s']:.6f}/1800 s；新单查询 7.434151 s，外推 {stops['quick_cost_projection_s']:.6f}/1800 s，中途并发背景下重估外推 {stops['reestimate_projection_s']:.6f}/1800 s。成功骨架最浅切入 {stops['winning_split_depth_min_m']:.9f} m；浅切入普通拒绝 51/208 失败尝试，非多数。三项 P0 违规为 0，完整合同排除清单始终 []。\n\n"
report += f"最终只读审计 {frozen['read_only_audit_wall_s']:.6f} s：冻结文件 {frozen['whole_files']}、符号 {frozen['symbols']}、owner {frozen['owner_files']}、输入 {frozen['input_files']}、配置 {frozen['configs']}、100 旧基线合同的 {baseline_count} 文件及两个冻结工作树差异均 0。源文件保持第 4 部分门禁后散列。\n\n"
report += f"独立后台监控正常刷盘退出；本轮 {resources['samples']} 个有效样本，坏行 {resources['invalid_lines']}，采集错误 {resources['sample_errors']}，最大间隔 {resources['max_sample_gap_s']:.6f} s；最低可用内存 {resources['min_available_gib']:.3f} GiB，提交量峰值 {resources['peak_committed_gib']:.3f} GiB（{resources['peak_commit_percent']}%）。本轮未重现整机卡死；这些接续数据不能证明之前卡死的原因。完整按 2 s 刷盘的系统采样、各阶段当前尝试与命令/PID 记录在外部 run；摘要与 SHA 索引在 part8_cost_ruling/。\n\n"
report += f"分支完整交付 SHA、ls-remote 原行和包含推送的总墙钟在 {external / 'final_push.json'}，避免提交内部自引用 SHA。研究接受仍待规划审查方复跑 P0，当前只报告执行检查通过。\n"
(DOC / "REPORT.md").write_text(report, encoding="utf-8", newline="\n")
running = (DOC / "RUNNING.md").read_text(encoding="utf-8")
old = "当前从 7b942db 按成本裁定恢复。第 1、2 部分接受，先单独提交新端点集合/按需扫描规则，再以单进程完成成本和真实 12 机专项检查，通过后按顺序继续；原输出不覆盖。后文旧停止状态为历史记录。"
assert old in running
running = running.replace(old, "当前第 1–8 部分执行检查完成，全部产物保留；最终研究接受待规划审查方复跑。下文旧停止状态和中间进度均为历史记录；最新结论见 REPORT 最后的成本裁定轮第 8 部分及 acceptance.json。不得重用既有输出目录。", 1)
running += f"\n最终监控已正常停止：{monitor}。资源摘要与索引见 part8_cost_ruling/。最终 SHA/远端核对见 {external / 'final_push.json'}。如需复查异常，先读 run/RECOVERY.md、system_monitor/session.json/current_job.json 与最近一轮 telemetry/*.current_attempt.json；用 analyze_resources.py <监控目录> --out <全新摘要路径> 读取，保留原始 metrics.jsonl，不将坏尾行算成功。\n"
running += "\n完整生产命令见 part5/6/7_cost_ruling 的运行器与 watchdog.argv。各批次均明确 --prewarm-from <run/prewarm/area_cost_ruling_r1/prewarm.json>；预建仅含字段/弦/扇区，worker 缓存 miss 在进程内计算，不写共享缓存。复跑固定 --workers 1，比较目录不排除文件。\n"
(DOC / "RUNNING.md").write_text(running, encoding="utf-8", newline="\n")
assert not audit()
job.update(status="finished", ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
dump(ROOT / "system_monitor/current_job.json", job)
print(json.dumps({"part8_pre_push_complete": True, "audit_changes": changes, "baseline_files": baseline_count,
                  "resources": {k: resources[k] for k in ("samples", "min_available_gib", "peak_committed_gib", "peak_commit_percent", "sample_errors")},
                  "elapsed_s_excluding_push": elapsed}, ensure_ascii=False), flush=True)
