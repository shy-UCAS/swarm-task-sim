"""V8-20 private task/survey whitelist. Shared V8-19 schemas remain unchanged."""
import copy
import math

from ..motion.intents.close_observation import DATA, MAP, SEQ, project, assert_no_runtime

SURVEY_KEYS = {"geometry","bounds_m","footprint_radius_m","grid_spacing_m","strip_count","strips_per_member","area_m2"}
SECTOR_KEYS = {"type","base_geometry","center_m","inner_offset_m","outer_offset_m","start_angle_rad","angle_span_rad","bounding_radius_m"}
BASE_KEYS = {"Circle": {"type","center_m","radius_m"}, "Polygon": {"type","vertices_m"},
             "BufferedPolygon": {"type","vertices_m","buffer_m"}}


def _finite(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError("finite physical scalar required")
    return value


def _point(value):
    if not isinstance(value,(list,tuple)) or len(value) != 2:
        raise ValueError("xy pair required")
    for v in value:
        _finite(v)


def validate_survey(survey):
    assert_no_runtime(survey,"survey")
    if not isinstance(survey,dict) or set(survey) != SURVEY_KEYS:
        raise ValueError("survey requires its exact seven-key schema")
    sector = survey["geometry"]
    if not isinstance(sector,dict) or set(sector) != SECTOR_KEYS or sector["type"] != "ContourAnnularSector":
        raise ValueError("exact ContourAnnularSector schema required")
    base = sector["base_geometry"]
    if not isinstance(base,dict) or base.get("type") not in BASE_KEYS or set(base) != BASE_KEYS[base["type"]]:
        raise ValueError("unsupported or polluted base geometry")
    if base["type"] == "Circle":
        _point(base["center_m"])
        if _finite(base["radius_m"]) <= 0:
            raise ValueError("positive base radius required")
    else:
        vertices = base["vertices_m"]
        if not isinstance(vertices,(list,tuple)) or len(vertices) < 3:
            raise ValueError("polygon vertices required")
        for p in vertices:
            _point(p)
        if base["type"] == "BufferedPolygon" and _finite(base["buffer_m"]) < 0:
            raise ValueError("nonnegative base buffer required")
    _point(sector["center_m"])
    for k in ("inner_offset_m","outer_offset_m","start_angle_rad","angle_span_rad","bounding_radius_m"):
        _finite(sector[k])
    if not sector["inner_offset_m"] < sector["outer_offset_m"] or not 0 < sector["angle_span_rad"] <= 2*math.pi or sector["bounding_radius_m"] <= 0:
        raise ValueError("invalid sector extent")
    bounds = survey["bounds_m"]
    if not isinstance(bounds,(list,tuple)) or len(bounds) != 4:
        raise ValueError("four survey bounds required")
    for value in bounds:
        _finite(value)
    if not bounds[0] < bounds[2] or not bounds[1] < bounds[3]:
        raise ValueError("positive survey bounds required")
    for k in ("footprint_radius_m","grid_spacing_m","area_m2"):
        if _finite(survey[k]) <= 0:
            raise ValueError("positive survey scale required")
    c,k = survey["strips_per_member"],survey["strip_count"]
    if type(c) is not int or c < 2 or c%2 or type(k) is not int or k < c or k%c:
        raise ValueError("even c and complete member strip blocks required")
    return copy.deepcopy(survey)


def task_record(task):
    """Keep the original five TaskSpec fields and append only a formed private survey."""
    survey = getattr(task,"survey",None)
    if task.intent != "area_search" and survey is not None:
        raise ValueError("survey is private to area_search")
    out = {k:getattr(task,k) for k in ("task_id","intent","target_id","switch_mode","final")}
    if task.intent == "area_search" and survey is not None:
        out["survey"] = validate_survey(survey)
    return out
