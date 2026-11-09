"""V8-20 independent full member references using the frozen nominal backend."""
import numpy as np


def references_area_search(skeleton, *, warnings=None, target_id=None, band_m=None, align_m=None):
    from ..sim.tracking import TimeReference
    from .nominal import member_nominal
    from .skeleton import NominalPVA, reference_guidance, semantic_lines
    witnesses = skeleton.witnesses or {}
    if witnesses.get("intent") != "area_search":
        raise ValueError("explicit area_search skeleton required")
    independent = witnesses["independent_members"]
    if set(independent) != set(skeleton.members) or not independent:
        raise ValueError("independent geometry required for every member")
    refs, lines, maps = [], [], {}
    guidance = reference_guidance()
    for mid in sorted(skeleton.members):
        mp = skeleton.members[mid]
        nom = member_nominal(mp, guidance=guidance)
        pva = NominalPVA(nom)
        release = float(nom.release_s)
        end = release + float(nom.travel_s)
        refs.append(TimeReference(mid,release,end,float(nom.altitude_m),pva))
        anchors = independent[mid]
        phase_s = {k: float(anchors[k]) for k in ("collect_s","split_s","scan_start_s","scan_end_s",
                                                  "warning_entry_s","warning_exit_s","terminal_s")}
        maps[mid] = {"curve_s": np.asarray(nom.curve.s,float), "t_abs": pva.tn+pva.r,
                     "nominal": nom, "phase_s": phase_s}
        if warnings is not None:
            lines.extend(semantic_lines(mid,nom,warnings,target_id,band_m=band_m,align_m=align_m))
    return tuple(refs), tuple(lines), maps
