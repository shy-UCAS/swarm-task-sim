"""单编组联合时空优化（V8-13 第 3 部分，指令 3.1–3.5；附录第 3 节裁定 9.2、第 4 节简化）。

表示：每成员一条均匀三次 B 样条，节点 h·(−3..M+3)，M=ceil(T/h)，控制点 M+3，评价域截在 [0,T]（局部秒，
以 release 为原点）；时间分配固定，不改 release/end。在节点区间 [kh,(k+1)h] 上
p(u) = [1,u,u²,u³]·M_B·[c_k..c_{k+3}]，u=(t−kh)/h，导数按链式法则逐阶求（与 Cox–de Boor 递推同一组基）。

等式：p(0)=p_init、p(T)=p_end、v=a=0（两端），语义直线对与开区间相交的每个基函数支撑加 n·(c_k−q)=0。
按变量连通块做带主元 QR 消元 c = c* + Z z；秩冲突返回 optimize_equalities_inconsistent 及见证。

求解形式（V8-13b 裁定 2.1、2.2）：PHR 增广拉格朗日，内层 L-BFGS-B。
目标 f = F_ref + λ_j·F_smooth（λ_j = 1；F_ref 在"绝对 0.1 s 网格 ∪ 移动端点 ∪ 节点"上梯形积分并除以 Σ_i T_i，
F_smooth 按节点区间解析求和）。不等式约束 g_k ≤ 0 逐采样点（与 V8-13 指令 3.3 同一批点）、无量纲、阈值取附录
裁定 9.2 的缓冲值：间距 (3.25−d)/3（共同可见 10 Hz 帧）、几何 −(g_c−1)/m_c（m_c = 35/10）、速度 ‖v‖/(0.95·12)−1、
法向 a_n/(0.95·3)−1、切向 |a_t|/(0.95·2)−1、jerk ‖j‖/(0.95·J_plan)−1（每节点区间一个）。
L(c;λ,ρ) = f + (ρ/2)·Σ_k max(0, g_k + λ_k/ρ)² − Σ_k λ_k²/(2ρ)。
外循环：λ=0、ρ=1；每轮内层 L-BFGS-B（maxiter 200，SciPy 默认 ftol/gtol，热启动）后用原阈值硬检查，通过即结束；
否则 λ_k ← max(0, λ_k + ρ·g_k)，最大违反量未降到上一轮 1/4 以下则 ρ ← 10ρ；最多 8 轮。成功 = 有限且硬检查全过。

预条件：H0 = Zᵀ(∂²(F_ref+λ_j F_smooth)/∂c²)Z，按成员带状 Cholesky H0=UᵀU，变量 y=Uz。
初值：带等式的加权最小二乘骨架投影；精确对称冲突时一次确定性破对称。之后 L-BFGS-B 只调用一次。

本模块导入时不读配置、不读场景、不建目录；不导入 shapely。
"""
import math
import time
from dataclasses import dataclass, field as dc_field
from functools import cached_property

import numpy as np

EPS = float(np.finfo(np.float64).eps)
MB = np.array([[1.0, 4.0, 1.0, 0.0],
               [-3.0, 0.0, 3.0, 0.0],
               [3.0, -6.0, 3.0, 0.0],
               [-1.0, 3.0, -3.0, 1.0]]) / 6.0
FRAME_S = 0.1
REQUIRED_KEYS = ("jerk_plan_m_s3", "knot_s", "weight_smooth", "maxiter", "alm_max_rounds", "alm_rho0",
                 "alm_rho_growth", "alm_violation_ratio", "buffer_separation_m", "buffer_geometry_m",
                 "buffer_dynamic_factor")
WEIGHT_KEYS = ("weight_smooth",)


class SettingsIncomplete(ValueError):
    """joint_opt 配置缺键或权重非正：前提未完成，不能进入 solve_joint。"""


# ---------------------------------------------------------------- 数据合同

@dataclass(frozen=True)
class JointProblem:
    references: tuple          # TimeReference，按 member_id 排序
    clearances: tuple = ()     # 现有 Clearance，生产含 world/所有障碍/所有 alert
    field: object = None       # 现有 DistanceField；纯无障碍夹具可为 None
    lines: tuple = ()          # (member_id, t0, t1, point_xy, unit_tangent_xy)


@dataclass(frozen=True)
class JointSolution:
    ok: bool
    references: dict           # member_id -> SplineTrajectory；失败仍保留最后迭代供诊断
    reason: str | None         # optimize_not_converged / optimize_residual / ...
    diagnostics: dict


@dataclass(frozen=True)
class SplineTrajectory:
    member_id: str
    release_s: float
    end_s: float
    altitude_m: float
    knots: np.ndarray          # 局部秒（release 为原点），h·(−3..M+3)
    controls: np.ndarray       # (M+3, 2) 真实 ENU 平面米值

    @property
    def h(self):
        return float(self.knots[4] - self.knots[3])

    @property
    def duration(self):
        return float(self.end_s - self.release_s)

    def evaluate(self, t_abs_s, order=0):
        t = np.asarray(t_abs_s, float)
        shape = t.shape
        tau = t.reshape(-1) - float(self.release_s)
        T = self.duration
        inside = (tau >= 0.0) & (tau <= T)
        tc = np.clip(tau, 0.0, T)
        M = len(self.knots) - 7
        k, W = basis_weights(tc, self.h, M, order)
        C = np.asarray(self.controls, float)
        idx = k[:, None] + np.arange(4)[None, :]
        out = np.einsum("nj,njd->nd", W, C[idx])
        if order > 0:
            out = np.where(inside[:, None], out, 0.0)
        return out.reshape(shape + (2,))

    @cached_property
    def _pp(self):
        """每个节点区间以局部 τ−kh 为变量的三次多项式系数 (M, 4, 2)。"""
        C = np.asarray(self.controls, float)
        M = len(self.knots) - 7
        idx = np.arange(M)[:, None] + np.arange(4)[None, :]
        co = np.einsum("ij,kjd->kid", MB, C[idx])
        return co * (self.h ** -np.arange(4.0))[None, :, None]

    def pva(self, t_abs_s):
        if np.ndim(t_abs_s) != 0:
            return self.evaluate(t_abs_s, 0), self.evaluate(t_abs_s, 1), self.evaluate(t_abs_s, 2)
        tau = float(t_abs_s) - float(self.release_s)
        T = self.duration
        inside = 0.0 <= tau <= T
        tc = min(max(tau, 0.0), T)
        pp = self._pp
        k = min(int(math.floor(tc / self.h)), len(pp) - 1)
        x = tc - k * self.h
        c0, c1, c2, c3 = pp[k]
        p = c0 + x * (c1 + x * (c2 + x * c3))
        if not inside:
            return p, np.zeros(2), np.zeros(2)
        return p, c1 + x * (2.0 * c2 + 3.0 * x * c3), 2.0 * c2 + 6.0 * x * c3


# ---------------------------------------------------------------- 配置

def load_settings():
    """返回扁平数值 dict；从 load_config("joint_opt").values 读取，缺项报错。"""
    from ..config import load_config
    cfg = load_config("joint_opt")
    vals = dict(cfg.values)
    missing = [k for k in REQUIRED_KEYS if k not in vals]
    if missing:
        raise SettingsIncomplete(f"joint_opt 缺少 {missing}（第 2/3 部分测量未完成，不能默认补数）")
    bad = [k for k in WEIGHT_KEYS if not vals[k] > 0.0]
    if bad:
        raise SettingsIncomplete(f"joint_opt 权重须为正：{bad}")
    vals["_sha256"] = cfg.sha256
    return vals


def physical_limits(settings):
    """原业务上限（硬检查用）：均从冻结配置读取，不维护第二套阈值。"""
    from task_v07.criteria import load_criteria
    from ..config import load_config
    from ..sim.kernel import member_config
    G = load_config("guidance").values
    S = load_config("sim").values
    mon = load_config("monitoring").values
    prof = member_config().vehicle_profile
    return {"v_max": float(prof.max_speed_xy_m_s), "a_n": float(G["a_lat_m_s2"]), "a_t": float(G["a_lon_m_s2"]),
            "jerk": float(settings["jerk_plan_m_s3"]),
            "d_lane": float(load_criteria()["quality"]["min_separation_error_m"]) + 2.0 * float(mon["tracking_tube_m"]),
            "hold_s": float(S["terminal_hold_s"])}


# ---------------------------------------------------------------- 基函数

def basis_weights(tau, h, M, order):
    """返回 (区间号 k, 权重 (N,4))：p^{(order)}(τ) = Σ_j W[:,j]·c_{k+j}。"""
    tau = np.asarray(tau, float)
    k = np.clip(np.floor(tau / h).astype(np.int64), 0, M - 1)
    u = tau / h - k
    one, zero = np.ones_like(u), np.zeros_like(u)
    if order == 0:
        U = np.stack([one, u, u * u, u * u * u], axis=1)
    elif order == 1:
        U = np.stack([zero, one, 2 * u, 3 * u * u], axis=1) / h
    elif order == 2:
        U = np.stack([zero, zero, 2 * one, 6 * u], axis=1) / h ** 2
    elif order == 3:
        U = np.stack([zero, zero, zero, 6 * one], axis=1) / h ** 3
    else:
        raise ValueError("order 取 0–3")
    return k, U @ MB


def basis_csr(tau, h, M, n, order):
    from scipy.sparse import csr_matrix
    k, W = basis_weights(tau, h, M, order)
    N = len(k)
    rows = np.repeat(np.arange(N), 4)
    cols = (k[:, None] + np.arange(4)[None, :]).ravel()
    return csr_matrix((W.ravel(), (rows, cols)), shape=(N, n))


def _trapezoid(ts):
    w = np.zeros_like(ts)
    if len(ts) > 1:
        d = np.diff(ts)
        w[:-1] += d / 2
        w[1:] += d / 2
    return w


# ---------------------------------------------------------------- 等式消元

class EqualityInconsistent(ValueError):
    def __init__(self, member, witness):
        super().__init__(f"成员 {member} 的等式不相容")
        self.member = member
        self.witness = witness


def _eliminate(nvar, rows, member):
    """rows: [(dict 变量→系数, rhs)]。返回 (c_star (nvar,), Z (nvar×nz) CSR, free_vars, blocks_info)。"""
    from scipy.linalg import qr, solve_triangular
    from scipy.sparse import csr_matrix
    parent = list(range(nvar))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for coefs, _ in rows:
        vs = list(coefs)
        for v in vs[1:]:
            ra, rb = find(vs[0]), find(v)
            if ra != rb:
                parent[rb] = ra
    comp_rows = {}
    for ri, (coefs, _) in enumerate(rows):
        comp_rows.setdefault(find(next(iter(coefs))), []).append(ri)
    c_star = np.zeros(nvar)
    constrained = np.zeros(nvar, bool)
    cols_entries = []          # (锚变量, {var: value})
    info = []
    for root, ridx in sorted(comp_rows.items()):
        vars_ = sorted({v for ri in ridx for v in rows[ri][0]})
        pos = {v: i for i, v in enumerate(vars_)}
        A = np.zeros((len(ridx), len(vars_)))
        b = np.zeros(len(ridx))
        for a, ri in enumerate(ridx):
            for v, cval in rows[ri][0].items():
                A[a, pos[v]] = cval
            b[a] = rows[ri][1]
        m, k = A.shape
        smax = float(np.linalg.norm(A, 2)) if A.size else 0.0
        Q, R, P = qr(A, pivoting=True)
        diag = np.abs(np.diag(R)) if min(m, k) else np.zeros(0)
        tol = EPS * max(m, k) * smax
        r = int(np.sum(diag > tol))
        qb = Q.T @ b
        xp = np.zeros(k)
        if r:
            xp[:r] = solve_triangular(R[:r, :r], qb[:r])
        x = np.zeros(k)
        x[P] = xp
        resid = A @ x - b
        rtol = EPS * max(m, k) * (smax * float(np.linalg.norm(x)) + float(np.linalg.norm(b)))
        if float(np.linalg.norm(resid)) > rtol:
            raise EqualityInconsistent(member, {"vars": vars_, "A": A.tolist(), "b": b.tolist(), "rank": r,
                                                "residual": resid.tolist(), "tolerance": rtol})
        for i, v in enumerate(vars_):
            c_star[v] = x[i]
            constrained[v] = True
        if r < k:
            N12 = solve_triangular(R[:r, :r], R[:r, r:]) if r else np.zeros((0, k - r))
            Nperm = np.vstack([-N12, np.eye(k - r)])
            Nmat = np.zeros((k, k - r))
            Nmat[P] = Nperm
            for j in range(k - r):
                anchor = vars_[P[r + j]]
                entries = {vars_[i]: Nmat[i, j] for i in range(k) if Nmat[i, j] != 0.0}
                cols_entries.append((anchor, entries))
        info.append({"vars": len(vars_), "rows": m, "rank": r})
    for v in range(nvar):
        if not constrained[v]:
            cols_entries.append((v, {v: 1.0}))
    cols_entries.sort(key=lambda e: e[0])
    data, ri, ci = [], [], []
    for j, (_, ent) in enumerate(cols_entries):
        for v, val in ent.items():
            ri.append(v)
            ci.append(j)
            data.append(val)
    Z = csr_matrix((data, (ri, ci)), shape=(nvar, len(cols_entries)))
    free = np.array([a for a, _ in cols_entries], dtype=np.int64)
    return c_star, Z, free, info


# ---------------------------------------------------------------- 距离场（双线性 + 栅格外 Lipschitz 延拓）

class _FieldEval:
    def __init__(self, field, clearances, buffer_m):
        self.ok = field is not None and len(clearances) > 0
        if not self.ok:
            return
        self.x0, self.y0, self.g = field.x0, field.y0, field.spacing_m
        self.nx, self.ny, self.eps = field.nx, field.ny, field.eps
        self.items = []
        for c in clearances:
            grid = np.asarray(field.values[c.name], float)
            self.items.append((c.name, grid, float(c.minimum_m)))
        self.buffer = buffer_m

    def eval(self, pts, grid):
        gx = (pts[:, 0] - self.x0) / self.g
        gy = (pts[:, 1] - self.y0) / self.g
        cx = np.clip(gx, 0.0, self.nx - 1)
        cy = np.clip(gy, 0.0, self.ny - 1)
        ix = np.clip(np.floor(cx).astype(np.int64), 0, self.nx - 2)
        iy = np.clip(np.floor(cy).astype(np.int64), 0, self.ny - 2)
        fx = np.clip(cx - ix, 0.0, 1.0)
        fy = np.clip(cy - iy, 0.0, 1.0)
        f00, f10 = grid[iy, ix], grid[iy, ix + 1]
        f01, f11 = grid[iy + 1, ix], grid[iy + 1, ix + 1]
        val = f00 * (1 - fx) * (1 - fy) + f10 * fx * (1 - fy) + f01 * (1 - fx) * fy + f11 * fx * fy - self.eps
        dx = ((f10 - f00) * (1 - fy) + (f11 - f01) * fy) / self.g
        dy = ((f01 - f00) * (1 - fx) + (f11 - f10) * fx) / self.g
        ox = (gx - cx) * self.g
        oy = (gy - cy) * self.g
        out = (ox != 0.0) | (oy != 0.0)
        if np.any(out):
            dist = np.hypot(ox, oy)
            val = np.where(out, val - dist, val)
            dx = np.where(ox != 0.0, 0.0, dx)
            dy = np.where(oy != 0.0, 0.0, dy)
            safe = np.where(out, dist, 1.0)
            dx = np.where(out, dx - ox / safe, dx)
            dy = np.where(out, dy - oy / safe, dy)
        return val, dx, dy


# ---------------------------------------------------------------- 准备

@dataclass
class _Member:
    mid: str
    r: float
    T: float
    h: float
    M: int
    n: int
    alt: float
    p0: np.ndarray
    p1: np.ndarray
    tau_e: np.ndarray
    w_e: np.ndarray
    S_e: np.ndarray
    sdir_e: np.ndarray
    B0: object
    B1: object
    B2: object
    D3: object
    lens: np.ndarray
    f0: int
    f1: int
    Bf: object
    Bf1: object
    c_star: np.ndarray
    Z: object
    free: np.ndarray
    U_ab: np.ndarray = None
    L_ab: np.ndarray = None
    ubw: int = 0
    off: int = 0
    nz: int = 0
    eq_info: list = dc_field(default_factory=list)
    line_rows: list = dc_field(default_factory=list)


class Prepared:
    def __init__(self, problem, settings, knot_s):
        t_start = time.perf_counter()
        self.problem = problem
        self.settings = settings
        self.lim = physical_limits(settings)
        self.L0 = self.lim["d_lane"]
        self.J0 = float(settings["jerk_plan_m_s3"])
        f = float(settings["buffer_dynamic_factor"])
        self.cap_v = f * self.lim["v_max"]
        self.cap_n = f * self.lim["a_n"]
        self.cap_t = f * self.lim["a_t"]
        self.cap_j = f * self.J0
        self.dbuf = float(settings["buffer_separation_m"])
        self.lam_j = float(settings["weight_smooth"])
        self.rho = float(settings["alm_rho0"])
        self.mult = {}
        self.knot_s = float(knot_s)
        self.hold = self.lim["hold_s"]
        refs = tuple(sorted(problem.references, key=lambda r: r.member_id))
        self.refs = refs
        self.geo = _FieldEval(problem.field, problem.clearances, float(settings["buffer_geometry_m"]))
        self.members = []
        for ref in refs:
            self.members.append(self._member(ref, problem.lines))
        self.sumT = float(sum(m.T for m in self.members))
        self.pairs = []
        for a in range(len(self.members)):
            for b in range(a + 1, len(self.members)):
                A, B = self.members[a], self.members[b]
                lo, hi = max(A.f0, B.f0), min(A.f1, B.f1)
                if hi >= lo:
                    self.pairs.append([a, b, lo, hi, np.array([1.0, 0.0])])
        self.pair_time = float(sum((p[3] - p[2] + 1) * FRAME_S for p in self.pairs))
        off = 0
        for m in self.members:
            m.off = off
            off += m.nz
        self.nvar = off
        self._precondition()
        self.x_ls = self._least_squares()
        self.x0, self.break_info = self._break_symmetry(self.x_ls)
        self.prep_s = time.perf_counter() - t_start

    def _member(self, ref, lines):
        from scipy.sparse import csr_matrix
        r, e = float(ref.release_s), float(ref.end_s)
        T = e - r
        h = self.knot_s
        M = max(1, math.ceil(T / h))
        n = M + 3
        p0 = np.asarray(ref.pva(r)[0], float).reshape(2)
        p1 = np.asarray(ref.pva(e)[0], float).reshape(2)
        # 评价点：绝对 0.1 s 网格 ∪ 端点 ∪ 节点（局部）
        g0, g1 = math.ceil(r * 10 - 1e-9), math.floor(e * 10 + 1e-9)
        grid = np.arange(g0, g1 + 1, dtype=np.int64) / 10.0 - r
        knots_in = h * np.arange(0, M + 1)
        knots_in = knots_in[knots_in <= T]
        tau = np.unique(np.concatenate([grid[(grid >= 0.0) & (grid <= T)], [0.0, T], knots_in]))
        w = _trapezoid(tau)
        S, Sv, _ = ref.pva(tau + r)
        S = np.asarray(S, float).reshape(-1, 2) - p0
        Sv = np.asarray(Sv, float).reshape(-1, 2)
        B0, B1, B2 = (basis_csr(tau, h, M, n, o) for o in (0, 1, 2))
        lens = np.minimum(h * np.arange(1, M + 1), T) - h * np.arange(M)
        lens = np.maximum(lens, 0.0)
        rows = np.repeat(np.arange(M), 4)
        cols = (np.arange(M)[:, None] + np.arange(4)[None, :]).ravel()
        D3 = csr_matrix((np.tile(MB[3] * 6.0 / h ** 3, M), (rows, cols)), shape=(M, n))
        f0 = math.ceil(r * 10 - 1e-9)
        f1 = math.floor((e + self.hold) * 10 + 1e-9)
        tf = np.clip(np.arange(f0, f1 + 1, dtype=np.int64) / 10.0 - r, 0.0, T)
        Bf = basis_csr(tf, h, M, n, 0)
        Bf1 = basis_csr(tf, h, M, n, 1)
        # 等式行（变量交错：2j+轴），坐标相对 p0
        eq = []
        for tau_e, target in ((0.0, np.zeros(2)), (T, p1 - p0)):
            for order in (0, 1, 2):
                k, W = basis_weights(np.array([tau_e]), h, M, order)
                for ax in (0, 1):
                    coefs = {}
                    for j in range(4):
                        if W[0, j] != 0.0:
                            coefs[2 * (int(k[0]) + j) + ax] = float(W[0, j])
                    eq.append((coefs, float(target[ax]) if order == 0 else 0.0))
        line_rows = []
        for (mid, t0, t1, q, tg) in lines:
            if mid != ref.member_id:
                continue
            tg = np.asarray(tg, float)
            tg = tg / np.hypot(tg[0], tg[1])
            nrm = np.array([-tg[1], tg[0]])
            q = np.asarray(q, float) - p0
            a, b = float(t0) - r, float(t1) - r
            rhs = float(nrm @ q)
            for j in range(n):
                if (j - 3) * h < b and (j + 1) * h > a:
                    coefs = {}
                    if nrm[0] != 0.0:
                        coefs[2 * j] = float(nrm[0])
                    if nrm[1] != 0.0:
                        coefs[2 * j + 1] = float(nrm[1])
                    eq.append((coefs, rhs))
                    line_rows.append((j, nrm, rhs))
        c_star, Z, free, info = _eliminate(2 * n, eq, ref.member_id)
        return _Member(ref.member_id, r, T, h, M, n, float(ref.altitude_m), p0, p1, tau, w, S, Sv, B0, B1, B2,
                       D3, lens, f0, f1, Bf, Bf1, c_star, Z, free, nz=Z.shape[1], eq_info=info,
                       line_rows=line_rows)

    # -------------------------------------------------------- 预条件
    def _gram(self, m):
        from scipy.sparse import diags, kron, identity
        W = diags(m.w_e)
        G = (m.B0.T @ W @ m.B0) / self.L0 ** 2 + self.lam_j * (m.D3.T @ diags(m.lens) @ m.D3) / self.J0 ** 2
        G = G * (2.0 / self.sumT)
        return kron(G, identity(2), format="csr")

    def _precondition(self):
        from scipy.linalg import cholesky_banded, LinAlgError
        self.cond = []
        for m in self.members:
            if m.nz == 0:
                continue
            G2 = self._gram(m)
            H = (m.Z.T @ G2 @ m.Z).tocoo()
            u = int(np.max(H.col - H.row)) if H.nnz else 0
            ab = np.zeros((u + 1, m.nz))
            up = H.col >= H.row
            ab[u + H.row[up] - H.col[up], H.col[up]] = H.data[up]
            protect = 0.0
            try:
                U = cholesky_banded(ab, lower=False)
            except LinAlgError:
                Hn = float(np.max(np.abs(H.tocsr()).sum(axis=1)))
                protect = EPS * Hn
                ab2 = ab.copy()
                ab2[u] += protect
                try:
                    U = cholesky_banded(ab2, lower=False)
                except LinAlgError as exc:
                    raise _Conditioning(m.mid, str(exc))
            m.U_ab, m.ubw = U, u
            # 下三角带存储：L_ab[d, j] = Lmat[j+d, j] = U[j, j+d] = U_ab[u−d, j+d]
            L = np.zeros_like(U)
            for d in range(u + 1):
                L[d, :m.nz - d] = U[u - d, d:]
            m.L_ab = L
            self.cond.append({"member": m.mid, "nz": m.nz, "bandwidth": u, "protect": protect})

    def _z_from_y(self, m, y):
        from scipy.linalg import solve_banded
        return solve_banded((0, m.ubw), m.U_ab, y)

    def _y_from_z(self, m, z):
        U = m.U_ab
        u = m.ubw
        out = np.zeros_like(z)
        for d in range(u + 1):
            out[:m.nz - d] += U[u - d, d:] * z[d:]
        return out

    def _gy_from_gz(self, m, gz):
        from scipy.linalg import solve_banded
        return solve_banded((m.ubw, 0), m.L_ab, gz)

    # -------------------------------------------------------- 系数
    def coeffs(self, x):
        out = []
        for m in self.members:
            if m.nz:
                z = self._z_from_y(m, x[m.off:m.off + m.nz])
                c = m.c_star + m.Z @ z
            else:
                c = m.c_star.copy()
            out.append(c.reshape(m.n, 2))
        return out

    def _ls_grad_c(self, m, C):
        g = (m.B0.T @ ((m.B0 @ C - m.S_e) * m.w_e[:, None])) / self.L0 ** 2
        J = m.D3 @ C
        g = g + self.lam_j * (m.D3.T @ (J * m.lens[:, None])) / self.J0 ** 2
        return g * (2.0 / self.sumT)

    def _least_squares(self):
        from scipy.linalg import cho_solve_banded
        x = np.zeros(self.nvar)
        for m in self.members:
            if not m.nz:
                continue
            C = m.c_star.reshape(m.n, 2)
            gz = m.Z.T @ self._ls_grad_c(m, C).reshape(-1)
            z = -cho_solve_banded((m.U_ab, False), gz)
            x[m.off:m.off + m.nz] = self._y_from_z(m, z)
        return x

    # -------------------------------------------------------- 一次确定性破对称（3.4 第 4 条）
    def _break_symmetry(self, x):
        Cs = self.coeffs(x)
        info = {"pairs": [], "obstacle_points": 0, "applied": False}
        disp = [np.zeros((m.n, 2)) for m in self.members]
        wsum = [np.zeros(m.n) for m in self.members]
        for p in self.pairs:
            a, b, lo, hi, _ = p
            A, B = self.members[a], self.members[b]
            sa, sb = slice(lo - A.f0, hi - A.f0 + 1), slice(lo - B.f0, hi - B.f0 + 1)
            Pa = (A.Bf @ Cs[a])[sa] + A.p0
            Pb = (B.Bf @ Cs[b])[sb] + B.p0
            Va = (A.Bf1 @ Cs[a])[sa]
            Vb = (B.Bf1 @ Cs[b])[sb]
            dP, dV = Pa - Pb, Va - Vb
            d = np.hypot(dP[:, 0], dP[:, 1])
            cross = dP[:, 0] * dV[:, 1] - dP[:, 1] * dV[:, 0]
            hit = np.flatnonzero((d < self.dbuf) & (cross == 0.0))
            if not len(hit):
                continue
            rv = dV[hit[0]]
            nr = math.hypot(rv[0], rv[1])
            nvec = np.array([-rv[1], rv[0]]) / nr if nr > 0.0 else np.array([1.0, 0.0])
            p[4] = nvec
            gap = self.dbuf - d[hit]
            for mi, sl_lo, sign in ((a, lo - A.f0, 1.0), (b, lo - B.f0, -1.0)):
                mm = self.members[mi]
                rows = mm.Bf[sl_lo + hit]
                rows = rows.tocoo()
                dv = sign * 0.5 * gap[rows.row][:, None] * nvec[None, :]
                np.add.at(disp[mi], rows.col, rows.data[:, None] * dv)
                np.add.at(wsum[mi], rows.col, rows.data)
            info["pairs"].append({"pair": (A.mid, B.mid), "frames": int(len(hit)), "normal": nvec.tolist(),
                                  "max_gap_m": float(gap.max())})
        if self.geo.ok:
            for mi, m in enumerate(self.members):
                P = m.B0 @ Cs[mi] + m.p0
                sd = m.sdir_e
                sn = np.hypot(sd[:, 0], sd[:, 1])
                for name, grid, mc in self.geo.items:
                    val, gx, gy = self.geo.eval(P, grid)
                    gap = self.geo.buffer - val
                    nl = np.where(sn[:, None] > 0, np.stack([-sd[:, 1], sd[:, 0]], 1) / np.where(sn > 0, sn, 1)[:, None], 0.0)
                    lat = nl[:, 0] * gx + nl[:, 1] * gy
                    # 横向推移：方向取骨架切向的法向中余量增大的一侧（横向梯度精确为零时取左法向），
                    # 大小取当前缺口；只做这一次，不尝试两侧择优。
                    side = np.where(lat < 0.0, -1.0, 1.0)
                    hit = np.flatnonzero((gap > 0) & (sn > 0))
                    if not len(hit):
                        continue
                    rows = m.B0[hit].tocoo()
                    dv = (gap[hit] * side[hit])[rows.row][:, None] * nl[hit][rows.row]
                    np.add.at(disp[mi], rows.col, rows.data[:, None] * dv)
                    np.add.at(wsum[mi], rows.col, rows.data)
                    info["obstacle_points"] += int(len(hit))
        x1 = x.copy()
        for mi, m in enumerate(self.members):
            if not np.any(wsum[mi] > 0) or not m.nz:
                continue
            dc = np.where(wsum[mi][:, None] > 0, disp[mi] / np.where(wsum[mi] > 0, wsum[mi], 1.0)[:, None], 0.0)
            z = self._z_from_y(m, x[m.off:m.off + m.nz]) + dc.reshape(-1)[m.free]
            x1[m.off:m.off + m.nz] = self._y_from_z(m, z)
            info["applied"] = True
        return x1, info

    # -------------------------------------------------------- 增广拉格朗日（V8-13b 裁定 2.1）
    def _blocks(self, Cs, want_grad):
        """逐类不等式约束 g_k ≤ 0（无量纲，阈值为附录 9.2 缓冲值）。产出 (键, g, 回传函数)；
        回传函数 bp(coef) 把 Σ coef_k·∂g_k 累加到成员 p/v/a/j 梯度缓存。"""
        out = []
        gbuf = self._gbuf
        Pf = []
        for mi, m in enumerate(self.members):
            C = Cs[mi]
            P = m.B0 @ C
            V = m.B1 @ C
            A = m.B2 @ C
            J = m.D3 @ C
            self._pvaj[mi] = (P, V, A, J)
            s = np.hypot(V[:, 0], V[:, 1])
            pos = s > 0
            ss = np.where(pos, s, 1.0)
            u = V / ss[:, None]
            at = np.where(pos, u[:, 0] * A[:, 0] + u[:, 1] * A[:, 1], np.hypot(A[:, 0], A[:, 1]))
            Wv = A - at[:, None] * u
            an = np.where(pos, np.hypot(Wv[:, 0], Wv[:, 1]), 0.0)
            # 速度
            gv = s / self.cap_v - 1.0

            def bp_v(coef, mi=mi, V=V, ss=ss):
                gbuf[mi][1][:] += (coef / self.cap_v / ss)[:, None] * V
            out.append((("v", mi), gv, bp_v))
            # 切向
            gt = np.abs(at) / self.cap_t - 1.0

            def bp_t(coef, mi=mi, at=at, u=u, Wv=Wv, ss=ss, pos=pos, A=A):
                c = coef * np.sign(at) / self.cap_t
                gbuf[mi][2][:] += np.where(pos[:, None], c[:, None] * u, 0.0)
                gbuf[mi][1][:] += np.where(pos[:, None], (c / ss)[:, None] * Wv, 0.0)
                if np.any(~pos):
                    an0 = np.hypot(A[:, 0], A[:, 1])
                    sa = np.where(an0 > 0, an0, 1.0)
                    gbuf[mi][2][:] += np.where((~pos)[:, None], (coef / self.cap_t / sa)[:, None] * A, 0.0)
            out.append((("t", mi), gt, bp_t))
            # 法向
            gn = an / self.cap_n - 1.0

            def bp_n(coef, mi=mi, an=an, at=at, Wv=Wv, ss=ss, pos=pos):
                ok = pos & (an > 0) & (coef != 0.0)
                if np.any(ok):
                    q = np.zeros_like(coef)
                    q[ok] = coef[ok] / (an[ok] * self.cap_n)
                    gbuf[mi][2][:] += q[:, None] * Wv
                    q2 = np.zeros_like(coef)
                    q2[ok] = -q[ok] * (at[ok] / ss[ok])
                    gbuf[mi][1][:] += q2[:, None] * Wv
            out.append((("n", mi), gn, bp_n))
            # jerk（每个节点区间一个约束；长度为 0 的区间不计）
            jn = np.hypot(J[:, 0], J[:, 1])
            gj = np.where(m.lens > 0, jn / self.cap_j - 1.0, -1.0)

            def bp_j(coef, mi=mi, J=J, jn=jn):
                sj = np.where(jn > 0, jn, 1.0)
                gbuf[mi][3][:] += (coef / self.cap_j / sj)[:, None] * J
            out.append((("j", mi), gj, bp_j))
            # 几何
            if self.geo.ok:
                Pab = P + m.p0
                for ci, (name, grid, mc) in enumerate(self.geo.items):
                    val, gx, gy = self.geo.eval(Pab, grid)
                    gg = -(val - self.geo.buffer) / mc

                    def bp_g(coef, mi=mi, gx=gx, gy=gy, mc=mc):
                        gbuf[mi][0][:, 0] += -coef * gx / mc
                        gbuf[mi][0][:, 1] += -coef * gy / mc
                    out.append((("geo", mi, ci), gg, bp_g))
            Pf.append(m.Bf @ C + m.p0)
        self._Pf = Pf
        for pi, (a, b, lo, hi, nvec) in enumerate(self.pairs):
            A_, B_ = self.members[a], self.members[b]
            sa, sb = slice(lo - A_.f0, hi - A_.f0 + 1), slice(lo - B_.f0, hi - B_.f0 + 1)
            dP = Pf[a][sa] - Pf[b][sb]
            d = np.hypot(dP[:, 0], dP[:, 1])
            gs = (self.dbuf - d) / self.L0

            def bp_s(coef, a=a, b=b, sa=sa, sb=sb, dP=dP, d=d, nvec=nvec):
                sd = np.where(d > 0, d, 1.0)
                dirn = np.where((d > 0)[:, None], dP / sd[:, None], nvec[None, :])
                g = (-coef / self.L0)[:, None] * dirn
                self._gPf[a][sa] += g
                self._gPf[b][sb] -= g
            out.append((("sep", pi), gs, bp_s))
        return out

    def _alloc(self):
        self._gbuf = [[np.zeros((len(m.tau_e), 2)), np.zeros((len(m.tau_e), 2)), np.zeros((len(m.tau_e), 2)),
                       np.zeros((m.M, 2))] for m in self.members]
        self._gPf = [np.zeros((m.f1 - m.f0 + 1, 2)) for m in self.members]
        self._pvaj = [None] * len(self.members)

    def constraint_values(self, x):
        Cs = self.coeffs(x)
        self._alloc()
        return {k: g for k, g, _ in self._blocks(Cs, False)}

    def max_violation(self, x):
        vals = self.constraint_values(x)
        worst = 0.0
        for g in vals.values():
            if len(g):
                worst = max(worst, float(np.max(g)))
        return max(worst, 0.0)

    def update_multipliers(self, x):
        vals = self.constraint_values(x)
        for k, g in vals.items():
            lam = self.mult.get(k)
            if lam is None:
                lam = np.zeros_like(g)
            self.mult[k] = np.maximum(0.0, lam + self.rho * g)
        return vals

    def value_grad(self, x, *, terms=False):
        Cs = self.coeffs(x)
        self._alloc()
        sumT = self.sumT
        rho = self.rho
        F = {"ref": 0.0, "smooth": 0.0, "alm": 0.0}
        blocks = self._blocks(Cs, True)
        alm = 0.0
        for k, g, bp in blocks:
            lam = self.mult.get(k)
            if lam is None:
                shifted = g
                lam2 = 0.0
            else:
                shifted = g + lam / rho
                lam2 = float(np.sum(lam * lam))
            act = np.maximum(shifted, 0.0)
            alm += 0.5 * rho * float(np.sum(act * act)) - lam2 / (2.0 * rho)
            if np.any(act > 0):
                bp(rho * act)
        F["alm"] = alm
        gCs = []
        for mi, m in enumerate(self.members):
            P, V, A, J = self._pvaj[mi]
            w = m.w_e
            E = P - m.S_e
            F["ref"] += float(np.sum(w * (E[:, 0] ** 2 + E[:, 1] ** 2))) / self.L0 ** 2 / sumT
            gP = self._gbuf[mi][0] + 2.0 * w[:, None] * E / self.L0 ** 2 / sumT
            jn2 = J[:, 0] ** 2 + J[:, 1] ** 2
            F["smooth"] += float(np.sum(m.lens * jn2)) / self.J0 ** 2 / sumT
            gJ = self._gbuf[mi][3] + self.lam_j * 2.0 * m.lens[:, None] * J / self.J0 ** 2 / sumT
            gC = m.B0.T @ gP + m.B1.T @ self._gbuf[mi][1] + m.B2.T @ self._gbuf[mi][2] + m.D3.T @ gJ \
                + m.Bf.T @ self._gPf[mi]
            gCs.append(gC)
        total = F["ref"] + self.lam_j * F["smooth"] + alm
        grad = np.zeros(self.nvar)
        for mi, m in enumerate(self.members):
            if not m.nz:
                continue
            gz = m.Z.T @ gCs[mi].reshape(-1)
            grad[m.off:m.off + m.nz] = self._gy_from_gz(m, gz)
        if terms:
            return total, grad, F
        return total, grad

    def decode(self, x):
        out = {}
        for m, C in zip(self.members, self.coeffs(x)):
            knots = m.h * np.arange(-3, m.M + 4, dtype=float)
            out[m.mid] = SplineTrajectory(m.mid, m.r, m.r + m.T, m.alt, knots, C + m.p0)
        return out


class _Conditioning(Exception):
    def __init__(self, member, msg):
        super().__init__(msg)
        self.member = member


def prepare_problem(problem, settings, *, knot_s=1.0):
    """返回 Prepared：x0（一维归一变量）、value_grad(x)、decode(x)。"""
    return Prepared(problem, settings, knot_s)


def solve_joint(problem, settings, *, knot_s=1.0):
    """单次求解物理层（增广拉格朗日外循环 + 内层 L-BFGS-B）；返回 JointSolution，不重抽骨架。
    成功 = 结果有限且原阈值硬检查全过；SciPy success 只记录。外循环用完仍不过 → optimize_residual（附最坏约束）。"""
    from scipy.optimize import minimize
    from .optimize_checks import check_physical
    t0 = time.perf_counter()
    diag = {"knot_s": float(knot_s), "settings_sha256": settings.get("_sha256"), "rounds": []}
    try:
        prep = prepare_problem(problem, settings, knot_s=knot_s)
    except EqualityInconsistent as exc:
        diag.update(witness=exc.witness, member=exc.member, wall_s=time.perf_counter() - t0)
        return JointSolution(False, {}, "optimize_equalities_inconsistent", diag)
    except _Conditioning as exc:
        diag.update(member=exc.member, error=str(exc), wall_s=time.perf_counter() - t0)
        return JointSolution(False, {}, "optimize_conditioning", diag)
    diag.update(prepare_s=prep.prep_s, nvar=prep.nvar, conditioning=prep.cond, symmetry_break=prep.break_info)
    x = prep.x0
    v_prev = prep.max_violation(x)
    diag["initial_max_violation"] = v_prev
    rounds = int(settings["alm_max_rounds"])
    growth = float(settings["alm_rho_growth"])
    ratio = float(settings["alm_violation_ratio"])
    opts = {"maxiter": int(settings["maxiter"])}
    nit = nfev = 0
    phys = None
    passed = False
    finite = True
    solve_s = check_s = 0.0
    trajs = prep.decode(x)
    for r in range(rounds):
        ts = time.perf_counter()
        if prep.nvar:
            res = minimize(prep.value_grad, x, jac=True, method="L-BFGS-B", options=opts)
            x = res.x
            info = {"nit": int(res.nit), "nfev": int(res.nfev), "message": str(res.message),
                    "scipy_success": bool(res.success)}
        else:
            info = {"nit": 0, "nfev": 0, "message": "no free variables", "scipy_success": True}
        solve_s += time.perf_counter() - ts
        nit += info["nit"]
        nfev += info["nfev"]
        val, grad, F = prep.value_grad(x, terms=True)
        finite = bool(np.isfinite(val) and np.all(np.isfinite(x)))
        trajs = prep.decode(x)
        tc = time.perf_counter()
        phys = check_physical(problem, trajs, settings) if finite else {"passed": False, "failures": [
            {"kind": "nonfinite"}]}
        check_s += time.perf_counter() - tc
        info.update(round=r + 1, rho=prep.rho, value=val, terms=F, max_abs_grad=float(np.max(np.abs(grad)))
                    if len(grad) else 0.0, hard_passed=bool(phys["passed"]),
                    hard_failures=phys["failures"][:20])
        if finite and phys["passed"]:
            info["max_violation"] = prep.max_violation(x)
            diag["rounds"].append(info)
            passed = True
            break
        if not finite:
            diag["rounds"].append(info)
            break
        prep.update_multipliers(x)
        v = prep.max_violation(x)
        info["max_violation"] = v
        info["violation_ratio_vs_previous"] = (v / v_prev) if v_prev > 0 else None
        diag["rounds"].append(info)
        if not v <= ratio * v_prev:
            prep.rho *= growth
        v_prev = v
    diag.update(nit=nit, nfev=nfev, solve_s=solve_s, check_s=check_s, physical=phys,
                message=diag["rounds"][-1]["message"] if diag["rounds"] else None,
                success=passed, value=diag["rounds"][-1]["value"] if diag["rounds"] else None,
                terms=diag["rounds"][-1]["terms"] if diag["rounds"] else None,
                max_abs_grad=diag["rounds"][-1]["max_abs_grad"] if diag["rounds"] else None,
                outer_rounds=len(diag["rounds"]))
    diag["ls_controls"] = {m: t.controls for m, t in prep.decode(prep.x_ls).items()}
    diag["init_controls"] = {m: t.controls for m, t in prep.decode(prep.x0).items()}
    dev = []
    for m in prep.members:
        tr = trajs[m.mid]
        P = tr.evaluate(m.tau_e + m.r)
        e = np.hypot(*(P - (m.S_e + m.p0)).T)
        dev.append({"member": m.mid, "max_m": float(e.max()),
                    "rms_m": float(math.sqrt(np.sum(m.w_e * e ** 2) / m.T)) if m.T > 0 else 0.0})
    diag["reference_deviation"] = dev
    diag["wall_s"] = time.perf_counter() - t0
    if passed:
        return JointSolution(True, trajs, None, diag)
    return JointSolution(False, trajs, "optimize_residual", diag)


def optimize_segment(ctx, skeleton, key, settings):
    """从实际骨架建立问题，solve_joint 后运行全部语义硬检查；不能省略任何设施。
    skeleton 为 plan_attempt 返回的成功 SegmentPlan。返回 dict：ok、stage、reason、solution、monitoring、
    references、lines（含元数据）、problem。"""
    from .intents.monitoring import monitoring_constraints
    from .optimize_checks import check_monitoring
    from .skeleton import references_from_skeleton
    target = skeleton.witnesses["target_id"]
    cons = monitoring_constraints(ctx, target)
    base = tuple(cons["base"])
    field = ctx.field("route", list(base))
    refs, lines, maps = references_from_skeleton(
        skeleton, warnings=cons["warnings"], target_id=target,
        band_m=ctx.params["pre_entry_warning_clearance_m"], align_m=ctx.params["alignment_length_m"])
    problem = JointProblem(refs, base, field, tuple(tuple(l[:5]) for l in lines))
    sol = solve_joint(problem, settings, knot_s=float(settings["knot_s"]))
    out = {"ok": False, "stage": "optimize", "reason": sol.reason, "solution": sol, "monitoring": None,
           "references": refs, "lines": lines, "problem": problem, "maps": maps}
    if not sol.ok:
        return out
    mon = check_monitoring(ctx, skeleton, sol.references, settings)
    out["monitoring"] = mon
    if not mon["passed"]:
        out.update(stage="optimize_monitoring", reason="optimize_residual")
        return out
    out.update(ok=True, stage="optimized", reason=None)
    return out
