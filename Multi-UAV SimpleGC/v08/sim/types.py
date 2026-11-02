"""仿真适配层的数据对象、常量与异常。字段顺序是接口的一部分（按位置构造）。"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

FRAME_US = 100_000


class SimContractError(ValueError):
    """输入违反约定。"""


class TimelineInconsistent(RuntimeError):
    """统一时钟上的时间线不一致（r3 13.4）。"""
    code = "timeline_inconsistent"


@dataclass(frozen=True)
class MemberBoundaryState:
    """成员即将开始第 segment_index 段时的状态；tau_us 为编组统一时钟时刻（10 Hz 网格）。"""
    member_id: str
    segment_index: int
    tau_us: int
    p: tuple
    v: tuple
    a: tuple


@dataclass(frozen=True)
class MemberPiece:
    """一个速度小段：waypoints 第 0 点为起点，end_index 为小段终点下标，其后为延伸段。"""
    waypoints: tuple
    end_index: int
    speed_m_s: float


@dataclass(frozen=True)
class MemberSegmentPlan:
    """一个成员一段内的全部小段；出发延迟只用于第 0 段。"""
    member_id: str
    segment_index: int
    pieces: tuple
    release_delay_s: float = 0.0


@dataclass(frozen=True)
class PieceRecord:
    """每个小段的诊断记录。"""
    speed_m_s: float
    tau_start_us: int
    tau_end_us: int
    witness_local_us: Optional[int]
    crossing_local_frame: Optional[int]
    execution_status: str
    discarded_frames: int
    wall_s: float


@dataclass(frozen=True)
class MemberSegmentResult:
    member_id: str
    segment_index: int
    final: bool
    status: str
    tau_us: np.ndarray
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray
    end_state: Optional[MemberBoundaryState]
    executed_switch_tau_us: Optional[int]
    pieces: tuple


@dataclass(frozen=True)
class MemberTrack:
    """一个成员拼接到编组统一时钟上的完整轨迹。"""
    member_id: str
    tau_us: np.ndarray
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray
    segment_index: np.ndarray
    executed_switch_tau_us: tuple
