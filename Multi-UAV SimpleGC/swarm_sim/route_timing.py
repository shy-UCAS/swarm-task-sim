"""Compare raw waypoint event times with the bound per-phase nominal model."""
from .observations import finite_number


def nominal_arrival_evidence(scene, events, metadata, time_epoch):
    timing=scene.get("planning",{}).get("nominal_phase_timing",{})
    shift=metadata["run_epoch_monotonic_s"]-time_epoch
    records=[]; missing=[]; phases={}
    for phase_index,phase in enumerate(scene["phases"]):
        name=phase["name"]
        if name not in timing:
            continue
        model=timing[name]
        releases=[e["release_t"]+shift for e in events if e.get("event")=="phase_release_scheduled"
                  and e.get("phase")==name and finite_number(e.get("release_t"))]
        release=releases[0] if len(releases)==1 else None
        next_name=scene["phases"][phase_index+1]["name"] if phase_index+1<len(scene["phases"]) else None
        next_releases=[e["release_t"]+shift for e in events if e.get("event")=="phase_release_scheduled"
                       and e.get("phase")==next_name and finite_number(e.get("release_t"))] if next_name else []
        upper_bounds=[]
        if len(next_releases)==1: upper_bounds.append(next_releases[0])
        if finite_number(metadata.get("mission_end_monotonic_s")):
            upper_bounds.append(metadata["mission_end_monotonic_s"]-time_epoch)
        if finite_number(metadata.get("elapsed_s")):
            upper_bounds.append(metadata["elapsed_s"]+shift)
        end=min(upper_bounds) if upper_bounds else None
        bounds_valid=release is not None and end is not None and release<=end
        phase_records=[]; expected=0
        for agent,arrivals in model["per_agent_waypoint_arrival_s"].items():
            for index,nominal in enumerate(arrivals):
                expected+=1; seq=index+2
                hits=[e["t"]+shift for e in events if e.get("event")=="waypoint_reached" and e.get("phase")==name
                      and e.get("agent_id")==agent and type(e.get("seq")) is int and e["seq"]==seq and finite_number(e.get("t"))
                      and bounds_valid and release<=e["t"]+shift<=end]
                if not hits:
                    missing.append(dict(phase=name,agent_id=agent,seq=seq,reason="missing_bounds_or_in_phase_waypoint_event"))
                    continue
                actual=min(hits)-release
                row=dict(phase=name,agent_id=agent,seq=seq,route_index=index,actual_s=actual,nominal_s=nominal,
                         deviation_s=actual-nominal,tau_s=model["tau_s"],within_tau=abs(actual-nominal)<model["tau_s"],
                         release_s=release,event_s=min(hits),event_count=len(hits))
                records.append(row); phase_records.append(row)
        complete=len(phase_records)==expected and bounds_valid
        violation=any(not row["within_tau"] for row in phase_records)
        phases[name]=dict(tau_s=model["tau_s"],nominal_duration_s=model["duration_s"],
            release_s=release,end_s=end,
            expected_waypoints=expected,paired_waypoints=len(phase_records),complete=complete,
            max_abs_s=max((abs(row["deviation_s"]) for row in phase_records),default=None),
            within_tau=False if violation else True if complete else None)
    values=[p["within_tau"] for p in phases.values()]
    return dict(records=records,missing=missing,per_phase=phases,
        expected_waypoints=sum(p["expected_waypoints"] for p in phases.values()),paired_waypoints=len(records),
        complete=bool(phases) and all(p["complete"] for p in phases.values()),
        within_tau=False if False in values else True if values and all(v is True for v in values) else None,
        time_basis="raw waypoint receive monotonic time minus scheduled phase release; compared to bound uniform-speed route",
        criterion="abs(actual_s - nominal_s) < that phase's tau_s; missing evidence is unknown")
