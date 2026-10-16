"""A bounded search keeps its final actual failure and its complete history."""
from copy import deepcopy

FAILURE_CATEGORIES = frozenset(("geometry_pool_empty", "rehearsal_failure", "timing_conflict"))


def exhausted_failure(history):
    if not history or any(item["category"] not in FAILURE_CATEGORIES for item in history):
        raise ValueError("Each rejected calibration round needs one actual M2 failure category")
    return {"status": "rejected", "category": history[-1]["category"], "detail": history[-1]["detail"],
            "exhausted": True, "history": deepcopy(history)}
