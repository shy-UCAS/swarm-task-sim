"""逐成员分段仿真（第 4 部分实现）。"""


def append_extension(waypoints, length_m):
    raise NotImplementedError


def execute_recorded(skeleton, delays_s, *, only_agent):
    raise NotImplementedError


def run_member_segment(plan, state, *, final, config=None):
    raise NotImplementedError
