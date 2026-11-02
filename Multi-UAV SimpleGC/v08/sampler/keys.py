"""随机数键派生（r3 13.5）：每个抽签由一个不可变键唯一确定，与调用顺序无关。

键的规范串（JSON）取 SHA256，大端切成 8 个 32 位字作 SeedSequence 的 spawn_key；
family 名单独派生熵。模块无全局可变状态，同一键任何时候得到同一随机流。
"""
import hashlib
import json
from dataclasses import dataclass

import numpy as np

RNG_NAMESPACE = "traj2language-v08-rng-v1"
PURPOSES = ("common", "sequence", "branch", "formation", "strand", "shape", "connect", "speed", "offsets")


@dataclass(frozen=True)
class RngKey:
    family_id: str
    draw: int
    purpose: str
    mission: int | None = None
    branch: int | None = None
    group: str | None = None
    segment: int | None = None
    attempt: int = 0


def _is_nonneg_int(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _is_nonempty_str(x):
    return isinstance(x, str) and x != ""


def validate_key(key):
    if not isinstance(key, RngKey):
        raise ValueError(f"键必须是 RngKey，实际为 {type(key).__name__}")
    if not _is_nonempty_str(key.family_id):
        raise ValueError(f"family_id 必须是非空字符串：{key.family_id!r}")
    for name in ("draw", "attempt"):
        if not _is_nonneg_int(getattr(key, name)):
            raise ValueError(f"{name} 必须是非负整数：{getattr(key, name)!r}")
    if key.purpose not in PURPOSES:
        raise ValueError(f"purpose 不在 PURPOSES 中：{key.purpose!r}")
    for name in ("mission", "branch", "segment"):
        v = getattr(key, name)
        if v is not None and not _is_nonneg_int(v):
            raise ValueError(f"{name} 必须是 None 或非负整数：{v!r}")
    if key.group is not None and not _is_nonempty_str(key.group):
        raise ValueError(f"group 必须是 None 或非空字符串：{key.group!r}")
    if key.purpose == "common":
        for name in ("mission", "branch", "group", "segment"):
            if getattr(key, name) is not None:
                raise ValueError(f"公共抽签不得含任务成分：{name}={getattr(key, name)!r}")
    elif key.mission is None:
        raise ValueError(f"purpose={key.purpose!r} 必须给出 mission")


def family_entropy(family_id):
    return int(hashlib.sha256(f"{RNG_NAMESPACE}:family:{family_id}".encode("utf-8")).hexdigest(), 16)


def key_words(key):
    validate_key(key)
    c = json.dumps([RNG_NAMESPACE, key.family_id, key.draw, key.purpose, key.mission, key.branch,
                    key.group, key.segment, key.attempt], ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(c.encode("utf-8")).digest()
    return tuple(int.from_bytes(digest[i:i + 4], "big") for i in range(0, 32, 4))


def seed_sequence(key):
    validate_key(key)  # 先校验，非 RngKey 输入抛 ValueError 而不是取 family_id 时的 AttributeError
    return np.random.SeedSequence(entropy=family_entropy(key.family_id), spawn_key=key_words(key))


def rng_for(key):
    return np.random.Generator(np.random.PCG64(seed_sequence(key)))
