"""Versioned intent and planner contracts with explicit production registration."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class PlanResult:
    routes: dict
    assignments: dict
    diagnostics: dict


@dataclass(frozen=True)
class IntentSpec:
    name: str
    objectives: tuple[str, ...]
    semantic_phases: tuple[str, ...]
    service_phases: frozenset[str]
    normalize_params: Callable[[dict], dict]
    allowed_planners: tuple[str, ...]
    evaluate_channel: Callable[..., dict]
    validator_version: str
    behavior_labels: Callable[..., dict]
    required_audit_metrics: tuple[str, ...]
    topology_signature: Callable[[dict, dict], tuple] | None = None


@dataclass(frozen=True)
class PlannerSpec:
    name: str
    version: str
    normalize_params: Callable[[dict, dict], dict]
    plan_routes: Callable[[dict], PlanResult]


_intents, _planners = {}, {}

# Public vocabularies: new labels/roles have a single canonical spelling.
OBSERVED_MOTION_PATTERNS = {"parallel_strips": "平行往返", "perimeter_loop": "环绕",
                            "direct_passage": "直穿", "unclear": "未明确"}
SEMANTIC_ROLES = frozenset({"approach", "observe", "patrol", "transit", "return",
                            "idle_padding", "hold_no_op"})
FLIGHT_PATTERNS = {
    "reconnaissance": ("equal_strip_lawnmower", "interleaved_lanes"),
    "patrol": ("staggered_same_loop", "bidirectional_lanes"),
    "rapid_passage": ("line_abreast", "column"),
}


def component_versions(intent, flight_pattern):
    if flight_pattern not in FLIGHT_PATTERNS[intent]:
        raise ValueError("flight pattern does not belong to intent")
    return dict(planner=f"{flight_pattern}_v1", validator={
        "reconnaissance": "shared_coverage_v2", "patrol": "perimeter_revisit_v2",
        "rapid_passage": "rapid_passage_geometry_v1"}[intent],
        facts="observer_facts_v06", templates="templates_zh_v06")


def _initialize():
    if not _intents:
        from .reconnaissance import intent_spec, planner_spec
        from .patrol import intent_spec as patrol_intent, planner_spec as patrol_planner
        from .rapid_passage import intent_spec as passage_intent, planner_specs as passage_planners
        from .flight_patterns_v06 import interleaved_planner, bidirectional_planner
        _intents[intent_spec.name] = intent_spec
        _planners[planner_spec.name] = planner_spec
        _intents[patrol_intent.name] = patrol_intent
        _planners[patrol_planner.name] = patrol_planner
        _intents[passage_intent.name] = passage_intent
        for planner in (*passage_planners, interleaved_planner, bidirectional_planner):
            _planners[planner.name] = planner


def get_intent(name):
    _initialize()
    if not isinstance(name, str) or name not in _intents:
        raise ValueError(f"unregistered intent: {name!r}")
    return _intents[name]


def get_planner(name):
    _initialize()
    if not isinstance(name, str) or name not in _planners:
        raise ValueError(f"unregistered planner: {name!r}")
    return _planners[name]


def registered_intents():
    _initialize()
    return tuple(sorted(_intents))


def registered_planners():
    _initialize()
    return tuple(sorted(_planners))


@contextmanager
def temporary_registration(intent, planners=()):
    """Scope extension fixtures; never replace a production or outer registration.

    Fixtures belong in tests. No plugin is discovered from files or environment.
    Nested contexts and exceptions restore the exact prior registry state.
    """
    _initialize()
    if not isinstance(intent, IntentSpec) or not intent.name or intent.name in _intents:
        raise ValueError("intent must be a new IntentSpec")
    planners = tuple(planners)
    if any(not isinstance(p, PlannerSpec) or not p.name for p in planners):
        raise ValueError("planners must contain PlannerSpec objects")
    names = [p.name for p in planners]
    if len(set(names)) != len(names) or any(name in _planners for name in names):
        raise ValueError("planner registration already exists")
    if not set(intent.allowed_planners) <= (set(_planners) | set(names)):
        raise ValueError("intent references an unregistered planner")
    if (not intent.semantic_phases or len(set(intent.semantic_phases)) != len(intent.semantic_phases)
            or not intent.service_phases <= set(intent.semantic_phases)):
        raise ValueError("invalid intent semantic/service phases")
    old_intents, old_planners = dict(_intents), dict(_planners)
    try:
        _intents[intent.name] = intent
        _planners.update({p.name: p for p in planners})
        yield intent
    finally:
        _intents.clear()
        _intents.update(old_intents)
        _planners.clear()
        _planners.update(old_planners)
