"""统一时钟拼接（r3 8.4）：把各成员逐段仿真的结果按编组时钟连起来，只检查、不填充。

段与帧的归属：非最后一段占 [起点, 越过帧)，越过帧是下一段的第一帧；最后一段包含最后一帧。
"""
import numpy as np

from .types import FRAME_US, MemberTrack, TimelineInconsistent

STATE_TOL = 1e-9


def _fail(member, k, reason):
    raise TimelineInconsistent(f"成员 {member} 第 {k} 段：{reason}")


def _check_member(member, segs):
    count = len(segs)
    for k, s in enumerate(segs):
        if s.segment_index != k:
            _fail(member, s.segment_index, f"段号应依次为 0..{count - 1}，此处应为 {k}")
        if s.status != "ok":
            _fail(member, k, f"status 为 {s.status!r}，不是 'ok'")
        if bool(s.final) != (k == count - 1):
            _fail(member, k, "final 只能在最后一段为真" if s.final else "最后一段不是 final")
        n = len(s.tau_us)
        if n < 1:
            _fail(member, k, "没有帧")
        for name in ("p", "v", "a"):
            if len(getattr(s, name)) != n:
                _fail(member, k, f"{name} 帧数 {len(getattr(s, name))} 与 tau_us 帧数 {n} 不同")
    if int(segs[0].tau_us[0]) != 0:
        _fail(member, 0, f"第一帧 tau_us={int(segs[0].tau_us[0])}，不是 0")
    for prev, nxt in zip(segs, segs[1:]):
        k = prev.segment_index
        end = prev.end_state
        if end is None or prev.executed_switch_tau_us is None:
            _fail(member, k, "非最后一段缺 end_state 或 executed_switch_tau_us")
        t0 = int(nxt.tau_us[0])
        if not (end.tau_us == prev.executed_switch_tau_us == t0):
            _fail(member, k, f"切换时刻不一致：end_state.tau_us={end.tau_us}，"
                             f"executed_switch_tau_us={prev.executed_switch_tau_us}，下一段首帧={t0}")
        if end.segment_index != nxt.segment_index:
            _fail(member, k, f"end_state.segment_index={end.segment_index}，下一段为 {nxt.segment_index}")
        for name in ("p", "v", "a"):
            diff = np.abs(np.asarray(getattr(end, name), dtype=float) - np.asarray(getattr(nxt, name)[0], dtype=float))
            if not np.all(diff <= STATE_TOL):
                _fail(member, k, f"end_state.{name} 与下一段首帧相差 {float(diff.max())}")


def stitch(member_results):
    if not member_results:
        raise TimelineInconsistent("输入为空")
    groups = {}
    for r in member_results:
        groups.setdefault(r.member_id, []).append(r)
    for segs in groups.values():
        segs.sort(key=lambda s: s.segment_index)
    counts = {m: len(s) for m, s in groups.items()}
    if len(set(counts.values())) != 1:
        raise TimelineInconsistent(f"各成员段数不同：{counts}")

    out = {}
    for member in sorted(groups):
        segs = groups[member]
        _check_member(member, segs)
        tau = np.concatenate([np.asarray(s.tau_us, dtype=np.int64) for s in segs])
        steps = np.diff(tau)
        bad = np.flatnonzero(steps != FRAME_US)
        if len(bad):
            i = int(bad[0])
            seg_of = np.concatenate([np.full(len(s.tau_us), s.segment_index) for s in segs])
            _fail(member, int(seg_of[i + 1]), f"帧 {i}→{i + 1} 时间差 {int(steps[i])} µs，不是 {FRAME_US}（重复帧或空洞）")
        out[member] = MemberTrack(
            member_id=member,
            tau_us=tau,
            p=np.concatenate([np.asarray(s.p, dtype=float) for s in segs]),
            v=np.concatenate([np.asarray(s.v, dtype=float) for s in segs]),
            a=np.concatenate([np.asarray(s.a, dtype=float) for s in segs]),
            segment_index=np.concatenate([np.full(len(s.tau_us), s.segment_index, dtype=np.int64) for s in segs]),
            executed_switch_tau_us=tuple(int(s.executed_switch_tau_us) for s in segs[:-1]),
        )
    return out
