"""Independent abort facts from exported samples. No task_v07 imports."""
import numpy as np


def independent_abort(time_us, track, signed_distance, levels, endpoint, radius, complete):
    timestamps = np.asarray(time_us, dtype=np.int64)
    alerts = np.where(levels >= 2)[0]
    alert = int(alerts[0]) if alerts.size else None
    entered_protected = np.count_nonzero(levels >= 3) > 0
    turn = None
    leave = None
    arrival = None
    if alert is not None:
        # First occurrence of the minimum observed contour distance since alert entry.
        minimum = float(np.min(signed_distance[alert:]))
        turn = int(np.where(signed_distance[alert:] == minimum)[0][0]) + alert
        exterior = np.where(levels[turn:] < 1)[0]
        if exterior.size:
            leave = int(exterior[0]) + turn
            distances = np.sqrt(np.sum((track[leave:] - np.asarray(endpoint)) ** 2, axis=1))
            hits = np.where(distances <= radius)[0]
            if hits.size:
                arrival = int(hits[0]) + leave
    yes_or_missing = lambda value: True if value else False if complete else None
    conditions = {'abort_entered_alert': yes_or_missing(alert is not None),
                  'abort_no_protected_entry': False if entered_protected else True if complete else None,
                  'abort_left_warning_after_turn': yes_or_missing(leave is not None),
                  'abort_reached_retreat': yes_or_missing(arrival is not None)}
    def seconds(frame):
        return None if frame is None else int(timestamps[frame]) / 1_000_000
    facts = {'alert_entry_frame': alert, 'alert_entry_s': seconds(alert), 'entered_protected': bool(entered_protected),
             'turn_frame': turn, 'turn_s': seconds(turn), 'warning_exit_after_turn_frame': leave,
             'warning_exit_after_turn_s': seconds(leave), 'retreat_arrival_frame': arrival,
             'retreat_arrival_s': seconds(arrival), 'approached_then_withdrew': all(v is True for v in conditions.values())}
    return facts, conditions
