"""Compare a phase's uploaded NAV param1 with the onboard DataFlash CMD log.

CMD.CNum is only a mission-local sequence. Every phase clears and reuploads the
mission, so a sequence must also be bound to its aircraft and upload interval.
The clock fit maps FCU boot seconds to run-relative host receive seconds; it is
used only to identify the upload interval, not to infer firmware dwell timing.
"""

import math
from pathlib import Path

from .scenario import mission_for, route_mission_for
from .truth import clock_to_host


VERSION = "onboard_mission_param_check_v1"
TIME_MARGIN_S = 0.2


def read_onboard_commands(directory, agent, clock_model):
    """Read one fresh BIN; return mapped CMD records or an explicit limitation."""
    paths = sorted((Path(directory) / "sitl" / agent / "logs").glob("*.BIN"))
    if len(paths) != 1:
        return [], f"expected one fresh BIN, found {len(paths)}"
    if not clock_model.get("available"):
        return [], "FCU-to-host clock model unavailable"
    try:
        from pymavlink import DFReader

        reader = DFReader.DFReader_binary(str(paths[0]))
        records = []
        try:
            while (message := reader.recv_match(type="CMD")) is not None:
                packet = message.to_dict()
                source = packet.get("TimeUS")
                if (not isinstance(source, (float, int)) or isinstance(source, bool)
                        or not math.isfinite(source) or source < 0):
                    return [], "CMD has invalid TimeUS"
                source /= 1e6
                low, high = clock_model["source_range_s"]
                if low <= source <= high:
                    records.append(dict(packet=packet, source_boot_s=source,
                                        mapped_run_time_s=clock_to_host(source, clock_model)))
        finally:
            reader.close()
        return records, None
    except (OSError, ValueError, KeyError) as error:
        return [], f"cannot read/map CMD: {type(error).__name__}: {error}"


def compare_onboard_mission_params(scene, events, commands_by_agent, read_errors=None):
    """Return detailed per-(aircraft, phase, mission seq) evidence.

    `commands_by_agent` contains already time-mapped DataFlash CMD dictionaries,
    which keeps the matching rule independently testable without a BIN fixture.
    Missing, ambiguous, and conflicting evidence never becomes a pass.
    """
    read_errors = read_errors or {}
    required = scene["task_spec"]["execution"].get("hold_semantics") == "integer_seconds_v1"
    rows, counts = [], dict(pass_count=0, mismatch_count=0, unknown_count=0,
                           skipped_no_op_count=0, repeated_identical_count=0)
    upload_windows = {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        upload_windows[agent] = {}
        for phase in scene["phases"]:
            starts = [e["t"] for e in events if e.get("event") == "phase_upload_started"
                      and e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            ends = [e["t"] for e in events if e.get("event") == "phase_upload_complete"
                    and e.get("agent_id") == agent and e.get("phase") == phase["name"]]
            upload_windows[agent][phase["name"]] = (
                (starts[0], ends[0]) if len(starts) == len(ends) == 1 and starts[0] <= ends[0] else None)
    for phase in scene["phases"]:
        phase_name = phase["name"]
        semantic = (phase.get("semantic_phase")
                    or scene.get("semantic_plan", {}).get("execution_phases", {}).get(phase_name, {}).get("semantic_phase"))
        for vehicle in scene["vehicles"]:
            agent = vehicle["id"]
            route_mode = scene["schema_version"] == 2
            route = phase["routes"][agent] if route_mode else None
            if route_mode and not route:
                rows.append(dict(agent_id=agent, phase=phase_name, semantic_phase=semantic,
                                 status="skipped_no_op", reason="no mission uploaded"))
                counts["skipped_no_op_count"] += 1
                continue
            mission = (route_mission_for(vehicle, route, phase["speed_m_s"], phase["terminal_hold_s"], scene["origin"])
                       if route_mode else mission_for(vehicle, phase["targets"][agent], scene["origin"]))
            window = upload_windows[agent][phase_name]
            for seq in range(2, len(mission)):
                expected = mission[seq]
                row = dict(agent_id=agent, phase=phase_name, semantic_phase=semantic,
                           mission_seq=seq, route_index=seq-2, expected_command=expected["command"],
                           uploaded_param1=expected["params"][0], expected_CTot=len(mission),
                           upload_window_s=list(window) if window else None,
                           match_margin_s=TIME_MARGIN_S, onboard_records=[])
                if agent in read_errors:
                    row.update(status="unknown", reason=read_errors[agent])
                elif window is None:
                    row.update(status="unknown", reason="missing or ambiguous phase upload interval")
                else:
                    matches = [(index, record) for index, record in enumerate(commands_by_agent.get(agent, []))
                               if (window[0]-TIME_MARGIN_S <= record["mapped_run_time_s"]
                                   <= window[1]+TIME_MARGIN_S and record["packet"].get("CNum") == seq)]
                    row["onboard_records"] = [record for _, record in matches]
                    if not matches:
                        row.update(status="unknown", reason="onboard CMD missing for mission sequence")
                    elif any(other_name != phase_name and other_window is not None
                             and other_window[0]-TIME_MARGIN_S <= record["mapped_run_time_s"]
                             <= other_window[1]+TIME_MARGIN_S
                             for _, record in matches
                             for other_name, other_window in upload_windows[agent].items()):
                        row.update(status="unknown", reason="CMD time belongs to overlapping phase upload windows")
                    else:
                        signatures = {(record["packet"].get("CTot"), record["packet"].get("CId"),
                                       record["packet"].get("Prm1")) for _, record in matches}
                        if len(signatures) > 1:
                            row.update(status="mismatch", reason="conflicting CMD records for one phase/sequence")
                        else:
                            counts["repeated_identical_count"] += len(matches)-1
                            total, command, actual = next(iter(signatures))
                            if (total != len(mission) or command != expected["command"]
                                    or type(actual) not in (int, float) or not math.isfinite(actual)
                                    or not math.isclose(actual, expected["params"][0], abs_tol=1e-6, rel_tol=0)):
                                row.update(status="mismatch", reason="CMD CTot/CId/Prm1 differs from uploaded item")
                            else:
                                row.update(status="pass", reason=None)
                counts[row["status"]+"_count"] += 1
                rows.append(row)
    # A CMD record is deliberately never matched merely by CNum. The records
    # outside mapped upload intervals are retained in the source BIN and not
    # treated as evidence for any task item.
    status = ("mismatch" if counts["mismatch_count"] else "unknown" if counts["unknown_count"]
              else "pass")
    return dict(version=VERSION, required=required, status=status, pass_gate=(status == "pass") if required else None,
                key_fields=["agent_id", "semantic_phase", "phase", "mission_seq"],
                clock_semantics="BIN TimeUS mapped with v3 passive FCU-to-host clock; no extrapolation",
                matching_semantics="within this agent's phase upload interval, then CTot/CNum/CId/Prm1",
                counts=counts, read_errors=read_errors, rows=rows)


def diagnose_onboard_mission_params(directory, scene, events, clocks):
    records, errors = {}, {}
    for vehicle in scene["vehicles"]:
        agent = vehicle["id"]
        records[agent], error = read_onboard_commands(directory, agent, clocks[agent])
        if error:
            errors[agent] = error
    return compare_onboard_mission_params(scene, events, records, errors)
