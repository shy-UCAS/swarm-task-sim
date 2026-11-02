"""V8-09 2.1：高速软件在环标定航线（抽象几何：直线、90° 弯、两个 180° 掉头）。

route() 照抄执行指令第 2.1 节；元素编号 1–15 = prims 下标 + 1。
"""
import math
import numpy as np
from v08.calibration.geometry import line, arc

ALT_M = 30.0
SPACINGS = {"dense10": 10.0, "dense25": 25.0, "spline25": 25.0}
COMMANDS = {"dense10": 16, "dense25": 16, "spline25": 82}


def route(x0=-900.0, y0=-900.0, L=200.0):
    prims = []; p = np.array([x0, y0]); h = 0.0
    def straight(d):
        nonlocal p
        q = p + d * np.array([math.cos(h), math.sin(h)]); prims.append(line(tuple(p), tuple(q))); p = q
    def turn(R, deg, left):
        nonlocal p, h
        n = np.array([-math.sin(h), math.cos(h)]) * (1 if left else -1); c = p + R * n
        th0 = math.atan2(p[1] - c[1], p[0] - c[0]); dth = math.radians(deg) * (1 if left else -1)
        prims.append(arc(tuple(c), R, th0, dth)); a = th0 + dth
        p = c + R * np.array([math.cos(a), math.sin(a)]); h += dth
    straight(L)
    for R, left in ((320, True), (160, False), (80, True), (40, False), (20, True)):
        turn(R, 90, left); straight(L)
    turn(40, 180, True); straight(L); turn(20, 180, False); straight(L)
    return prims


def waypoints(mode):
    from v08.calibration.geometry import build_waypoints
    return build_waypoints(route(), SPACINGS[mode], ALT_M)


def elements():
    """[(编号, 元素)]，编号从 1 起。"""
    return list(enumerate(route(), start=1))
