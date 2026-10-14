"""Abort behavior facts on an observed 10 Hz prefix; no assigned core event."""
import numpy as np


def observed_abort(time_us, positions, contour_distance, target_levels, endpoint, radius, complete):
    def first(mask):
        found = np.flatnonzero(mask)
        return int(found[0]) if len(found) else None
    def positive(value):
        return True if value else False if complete else None
    seconds = np.asarray(time_us) / 1e6
    alert = first(target_levels >= 2)
    protected = bool(np.any(target_levels >= 3))
    turn = None if alert is None else alert + int(np.argmin(contour_distance[alert:]))
    exit_frame = None
    if turn is not None:
        hits = np.flatnonzero(target_levels[turn:] == 0)
        if len(hits):
            exit_frame = turn + int(hits[0])
    arrived = None
    if exit_frame is not None:
        hits = np.flatnonzero(np.linalg.norm(positions[exit_frame:] - endpoint, axis=1) <= radius)
        if len(hits):
            arrived = exit_frame + int(hits[0])
    conditions = {'abort_entered_alert': positive(alert is not None),
                  'abort_no_protected_entry': False if protected else True if complete else None,
                  'abort_left_warning_after_turn': positive(exit_frame is not None),
                  'abort_reached_retreat': positive(arrived is not None)}
    facts = {'alert_entry_frame': alert, 'alert_entry_s': None if alert is None else float(seconds[alert]),
             'entered_protected': protected, 'turn_frame': turn, 'turn_s': None if turn is None else float(seconds[turn]),
             'warning_exit_after_turn_frame': exit_frame,
             'warning_exit_after_turn_s': None if exit_frame is None else float(seconds[exit_frame]),
             'retreat_arrival_frame': arrived, 'retreat_arrival_s': None if arrived is None else float(seconds[arrived]),
             'approached_then_withdrew': all(v is True for v in conditions.values())}
    return facts, conditions
