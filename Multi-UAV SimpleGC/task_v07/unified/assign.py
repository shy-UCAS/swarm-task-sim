"""Monotone physical assignment within the already sampled public splits."""
import numpy as np
from task_v07.expansion.contracts import P0ContractError


def assign(members, starts, work_slots, public_split):
    stocks = public_split["members"]
    flattened = [a for stock in stocks for a in stock]
    if sorted(flattened) != sorted(members) or len(set(flattened)) != len(members):
        raise P0ContractError("Public split does not partition registered members")
    if {s["split_index"] for s in work_slots} != set(range(len(stocks))):
        raise P0ContractError("Work slots do not cover each public split")
    result = {}
    for i, stock in enumerate(stocks):
        slots = [s for s in work_slots if s["split_index"] == i]
        if len(slots) != len(stock) or len({s["slot_id"] for s in slots}) != len(slots):
            raise P0ContractError("Work slot count or identity mismatch")
        direction = np.asarray(slots[0]["direction"], float)
        normal = np.array([-direction[1], direction[0]])
        physical = sorted(stock, key=lambda a: (float(np.asarray(starts[a])[:2] @ normal), a))
        ordered = sorted(slots, key=lambda s: (float(np.asarray(s["entry"]) @ normal), s["slot_id"]))
        result.update(zip(physical, ordered))
    return result
