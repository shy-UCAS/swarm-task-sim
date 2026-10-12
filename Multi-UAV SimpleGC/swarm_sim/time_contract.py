"""Opt-in v0.6.1 common FCU-source seconds; host clocks are a calibration bridge.

The passive models do not identify transport delay. Composition preserves that
uncertainty and never extends either aircraft's measured clock support.
"""
import copy
import bisect
import math
import re

TIME_BASE = "sim_source"
REFERENCE_SELECTION_RULE = "natural_agent_id_ascending_then_exact_id; first_valid_model_covering_flight_epoch"


def _execution(value):
    value = value or {}
    return value.get("task_spec", value).get("execution", {})


def is_sim_time(scene_or_task):
    return _execution(scene_or_task).get("protocol_version") == "v0.6.1"


def sim_speedup(scene_or_task):
    if not is_sim_time(scene_or_task):
        return 1
    value = _execution(scene_or_task).get("sim_speedup", 1)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("sim_speedup must be a finite positive number")
    return value


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _agent_key(agent):
    return (tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                  for part in re.split(r"(\d+)", str(agent))), str(agent))


def _valid(model):
    knots = model.get("knots", [])
    return (model.get("available") is True and len(knots) >= 2
            and all(len(p) == 2 and all(_number(x) for x in p) for p in knots)
            and all(b[0] > a[0] and b[1] > a[1] for a, b in zip(knots, knots[1:])))


def _map(stamp, knots):
    from .truth import clock_to_host
    if not _number(stamp) or not knots[0][0] <= stamp <= knots[-1][0]:
        return None
    return clock_to_host(stamp, {"knots": knots})


class CommonTimeAxis:
    """Models map source boot seconds to host seconds relative to host_epoch_s."""
    def __init__(self, models, host_epoch_s=0.0):
        self.models = copy.deepcopy(models)
        models = self.models
        self._aligned_models = {}
        self.host_epoch_s = host_epoch_s
        self.reference_agent_id = None
        self.source_epoch_s = None
        self.reference = None
        rejected = []
        for agent in sorted(models, key=_agent_key):
            model = models[agent]
            epoch = _map(0.0, [(h, s) for s, h in model["knots"]]) if _valid(model) else None
            if epoch is not None:
                self.reference_agent_id, self.reference, self.source_epoch_s = agent, model, epoch
                break
            rejected.append(agent)
        self.available = self.reference is not None
        self.metadata = dict(time_base=TIME_BASE, available=self.available,
            reference_agent_id=self.reference_agent_id, reference_selection_rule=REFERENCE_SELECTION_RULE,
            reference_source_epoch_s=self.source_epoch_s, host_epoch_monotonic_s=host_epoch_s,
            rejected_reference_candidates=rejected, extrapolation=False, host_grid_fallback=False,
            mapping="f_reference^-1(f_agent(source_boot_s)) - reference_source_epoch_s",
            velocity_conversion=dict(input="FCU ENU velocity per aircraft source second",
                output="ENU velocity per common reference source second",
                rule="v_common = v_FCU * d(source_agent)/d(common_sim)",
                method="local piecewise clock Jacobian applied after native velocity interpolation on the common grid",
                knot_derivative="left segment at internal knots; first segment at lower support boundary",
                truth_velocity="SIM contains positions only; derived velocities already use common simulation seconds",
                raw_packets_preserved=True, extrapolation=False, position_difference_substitution=False),
            limitation="passive receive-clock bridge; transport delay not identified; not physical lockstep")
        if not self.available:
            self.metadata["reason"] = "no_valid_reference_clock_covering_flight_epoch"
        else:
            self.metadata["lifecycle_evidence_support_sim_s"] = [self.reference["knots"][0][0]-self.source_epoch_s,
                                                                self.reference["knots"][-1][0]-self.source_epoch_s]

    def host(self, relative_host_s):
        if not self.available:
            return None
        source = _map(relative_host_s, [(h, s) for s, h in self.reference["knots"]])
        return round(source - self.source_epoch_s, 12) if source is not None else None

    def source(self, agent, source_boot_s):
        model = self.aligned_model(agent)
        stamp = _map(source_boot_s, model["knots"]) if model["available"] else None
        return round(stamp, 12) if stamp is not None else None

    def aligned_model(self, agent):
        """Exact piecewise composition includes breakpoints of both models."""
        if agent in self._aligned_models:
            return self._aligned_models[agent]
        model = self.models.get(agent, {})
        if not self.available or not _valid(model):
            return dict(available=False, time_base=TIME_BASE, reason="clock_unavailable")
        inverse = [(h, s) for s, h in model["knots"]]
        reference_inverse = [(h, s) for s, h in self.reference["knots"]]
        low, high = max(inverse[0][0],reference_inverse[0][0]), min(inverse[-1][0],reference_inverse[-1][0])
        # Compose at shared HOST breakpoints: mapping inverse endpoints forward
        # again can round infinitesimally outside support and drop a valid edge.
        hosts = {low,high} | {host for host,_ in inverse + reference_inverse if low <= host <= high}
        knots = [(_map(host,inverse),round(_map(host,reference_inverse)-self.source_epoch_s,12))
                 for host in sorted(hosts)] if low < high else []
        if len(knots) < 2:
            return dict(available=False, time_base=TIME_BASE, reason="no_common_clock_support")
        result = dict(available=True, time_base=TIME_BASE, source_range_s=[knots[0][0], knots[-1][0]], knots=knots)
        self._aligned_models[agent] = result
        return result

    def velocity_factor(self, agent, stamp, *, time_base="agent_source"):
        """Return d(aircraft-source)/d(common-source), without extrapolation.

        A piecewise clock has no unique derivative at a knot. Select its left
        derivative, as clock_to_host does; the lower endpoint uses the first
        segment. This is a coordinate-unit conversion, not a measured derivative
        of positions and not a claim about absolute synchronization accuracy.
        """
        if time_base not in ("agent_source", TIME_BASE):
            raise ValueError("velocity conversion requires source or common simulation time")
        model = self.aligned_model(agent)
        if not model["available"] or not _number(stamp):
            return None
        knots = model["knots"]
        coordinate = 0 if time_base == "agent_source" else 1
        support = [p[coordinate] for p in knots]
        if not support[0] <= stamp <= support[-1]:
            return None
        if agent == self.reference_agent_id:
            return 1.0
        index = max(1, bisect.bisect_left(support, stamp))
        before, after = knots[index-1], knots[index]
        delta = after[1]-before[1]
        return (after[0]-before[0])/delta if delta > 0 else None

    def observation_velocities(self, agent, rows):
        """Convert interpolated FCU velocities at each common-grid instant.

        Positions and raw FCU packets are untouched. Applying the factor after
        resampling avoids smoothing a clock-Jacobian jump across a knot.
        """
        result = []
        for stamp, values in rows:
            factor = self.velocity_factor(agent, stamp, time_base=TIME_BASE)
            converted = ([*values[:3], *(component*factor for component in values[3:6])]
                         if values is not None and factor is not None else None)
            result.append((stamp, converted))
        return result

    def evaluation_model(self, agent):
        model = self.aligned_model(agent)
        if not model["available"]:
            return model
        low, high = model["knots"][0][1], model["knots"][-1][1]
        return dict(available=True, time_base=TIME_BASE, source_range_s=[low, high],
                    knots=[(low, low), (high, high)], method="bounded_common_source_seconds_identity")

    def grid(self, duration, hz):
        if duration is None or duration < 0:
            return []
        # Only remove floating arithmetic noise at exact simulation-frame edges.
        ticks = duration * hz
        if abs(ticks - round(ticks)) <= 1e-8:
            ticks = round(ticks)
        return [i / hz for i in range(math.floor(ticks) + 1)]

    def event_view(self, events, metadata):
        """Derived events only. Raw host receive and source timestamps survive."""
        shift = metadata["run_epoch_monotonic_s"] - self.host_epoch_s
        result = []
        for original in events:
            event = copy.deepcopy(original)
            for key in ("t", "release_t"):
                if _number(event.get(key)):
                    event["host_receive_" + key + "_s"] = original[key]
                    event[key] = self.host(original[key] + shift)
            event["time_base"] = TIME_BASE
            event["time_mapping_available"] = event.get("t") is not None
            result.append(event)
        return result

    def phase_start_spreads(self, events, scene):
        result = {}
        agents = {vehicle["id"] for vehicle in scene["vehicles"]}
        for phase in scene["phases"]:
            starts = [event for event in events if event.get("phase") == phase["name"]
                      and event.get("event") in ("phase_start_sent", "phase_no_op_started")]
            complete = (len(starts) == len(agents) and {event.get("agent_id") for event in starts} == agents
                        and all(_number(event.get("t")) for event in starts))
            result[phase["name"]] = max(event["t"] for event in starts)-min(event["t"] for event in starts) if complete else None
        return result

    def metadata_view(self, metadata):
        """Private evaluator view: all arithmetic operands share one time axis.

        Legacy key spellings are retained only inside evaluator adapters. The
        unmodified metadata is exported as source evidence, never this view.
        """
        result = copy.deepcopy(metadata)
        result["run_epoch_monotonic_s"] = 0.0
        result["flight_epoch_monotonic_s"] = 0.0
        end = self.host(metadata["run_epoch_monotonic_s"] + metadata["elapsed_s"] - self.host_epoch_s)
        if end is None and self.available:
            end = self.reference["knots"][-1][0] - self.source_epoch_s
        result["elapsed_s"] = end if end is not None else 0.0
        if "mission_end_monotonic_s" in metadata:
            mission_end = self.host(metadata["mission_end_monotonic_s"] - self.host_epoch_s)
            if mission_end is None:
                result.pop("mission_end_monotonic_s")
            else:
                result["mission_end_monotonic_s"] = mission_end
        result["time_base"] = TIME_BASE
        return result


def simulation_artifact(value):
    """Remove misleading legacy host-unit spellings from new semantic exports."""
    if isinstance(value, list):
        return [simulation_artifact(item) for item in value]
    if not isinstance(value, dict):
        return value
    renames = {"time_epoch_host_s": "time_epoch_sim_s", "barrier_wait_host_s": "barrier_wait_sim_s",
               "scheduling_wait_host_s": "scheduling_wait_sim_s", "armed_to_landed_host_s": "armed_to_landed_sim_s",
               "max_host_gap_s": "max_sim_gap_s"}
    return {renames.get(key, key): simulation_artifact(item) for key, item in value.items()}
