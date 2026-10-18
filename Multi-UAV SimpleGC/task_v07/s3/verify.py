"""Independent source-to-sentence verification (does not import facts/describe)."""
import math
import re
import statistics
import string

from ._common import P0ContractError, TEMPLATE_PATH, read_json, resolve_pointer

FORBIDDEN = ("悬停", "返航", "雷达", "天气", "风速", "风向", "指挥", "攻击", "打击",
             "摧毁", "敌", "规避", "威胁")


def check_forbidden(value):
    if isinstance(value, dict):
        for k, v in value.items():
            check_forbidden(k)
            check_forbidden(v)
    elif isinstance(value, (list, tuple)):
        for item in value:
            check_forbidden(item)
    elif isinstance(value, str):
        for word in FORBIDDEN:
            if word in value:
                raise P0ContractError(f"Forbidden word: {word}")


def load_templates(path=TEMPLATE_PATH):
    value = read_json(path)
    if len(value) != 16 or any(set(v) != {"A1", "A2", "B1", "B2"} for v in value.values()):
        raise P0ContractError("Template inventory is incomplete")
    check_forbidden(value)
    return value


def _expected(labels):
    yield "overview", None, False, []
    for gid in sorted(labels["task_groups"]):
        group = labels["task_groups"][gid]
        obs, ass = group["observed"], group["assigned"]
        gp = "/task_groups/" + gid
        paths = [f"/agents/{a}/observed/regions_by_facility/{ass['target']}/warning/entered_observed"
                 for a in obs["members"]]
        first = True
        if all(resolve_pointer(labels, p) is True for p in paths):
            kind = {"same_direction": "same", "multi_direction": "multi"}.get(obs["approach_classification"], "neutral")
            yield "approach_" + kind, gid, False, paths + [gp + "/observed/approach_classification"]
            first = False
        classification = obs["coordination"]["classification"]
        if classification in ("synchronous", "sequential"):
            yield ("coord_sync" if classification == "synchronous" else "coord_seq"), gid, first, [gp + "/observed/coordination/classification"]
            first = False
        if group["result"]["status"] == "success":
            yield "role_" + ass["execution_method"], gid, first, [gp + "/result/status", gp + "/assigned/execution_method"]
            first = False
        if ass["role"] != "intrusion":
            paths = [f"/agents/{a}/result/conditions/ended_outside_warning" for a in obs["members"]]
            values = [resolve_pointer(labels, p) for p in paths]
            if all(v is True for v in values):
                yield "exit_out", gid, first, [gp + "/assigned/role"] + paths
            elif all(v is False for v in values):
                yield "exit_in", gid, first, [gp + "/assigned/role"] + paths
    yield ("intent_conforms" if labels["cluster"]["result"]["status"] == "success" else "intent_insufficient"), None, False, ["/cluster/result/status"]


def _source_bindings(labels, gid, prefix):
    groups = resolve_pointer(labels, "/task_groups")
    n_groups = len(groups)
    names = dict(transit="过境", reconnaissance="侦察", monitoring="监视", feint="佯动", penetration="突防")
    values = {"n": len(resolve_pointer(labels, "/agents")),
              "grouping": "作为一个编组行动" if n_groups == 1 else f"分为{n_groups}个编组",
              "intent": names[resolve_pointer(labels, "/cluster/assigned/intent")]}
    refs = {"n": ["/agents"], "grouping": ["/task_groups"], "intent": ["/cluster/assigned/intent"]}
    if gid is None:
        return values, refs
    gp = "/task_groups/" + gid
    get = lambda suffix: resolve_pointer(labels, gp + suffix)
    members = get("/observed/members")
    index = sorted(groups).index(gid) + 1
    target = get("/assigned/target")
    match = re.fullmatch(r"facility_(\d+)", target)
    if match is None:
        raise P0ContractError(f"Invalid bound facility: {target}")
    sector = None
    paths = [gp + "/observed/approach_headings_deg/" + a for a in members]
    if get("/observed/approach_classification") == "same_direction":
        headings = [resolve_pointer(labels, p) for p in paths]
        if any(h is None for h in headings):
            raise P0ContractError(f"same_direction has None heading: {gid}")
        radians = [h * math.pi / 180 for h in headings]
        angle = math.degrees(math.atan2(statistics.mean(map(math.sin, radians)),
                                       statistics.mean(map(math.cos, radians))))
        bearing = (angle + 180) % 360
        sector = ("正东", "东北", "正北", "西北", "正西", "西南", "正南", "东南")[int((bearing + 22.5) % 360 // 45)]
    method = get("/assigned/execution_method")
    cov, dwell = None, None
    cov_refs = [gp + "/assigned/execution_method"]
    dwell_refs = [gp + "/assigned/execution_method"]
    if method == "area_search":
        cov_refs.append(gp + "/observed/shared_coverage/coverage_fraction")
        cov = round(resolve_pointer(labels, cov_refs[-1]) * 100 / 5) * 5
    if method == "close_observation":
        dwell_refs += [f"/agents/{a}/observed/contribution/observation_dwell/total_duration_s" for a in members]
        dwell = max(10, 10 * round(statistics.median([resolve_pointer(labels, p) for p in dwell_refs[1:]]) / 10))
    values.update(subj="该编组" if n_groups == 1 else f"第{index}编组（{len(members)}架）",
                  subj2="" if n_groups == 1 or prefix else "该编组", f=int(match[1]),
                  dir=sector, cov=cov, dwell=dwell, B=len(get("/observed/coordination/batches")))
    refs.update(subj=["/task_groups", gp + "/observed/members"], subj2=["/task_groups"],
                f=[gp + "/assigned/target"],
                dir=[gp + "/observed/approach_classification"] + paths,
                cov=cov_refs, dwell=dwell_refs, B=[gp + "/observed/coordination/batches"])
    return values, refs


def verify_description(record, labels, public_scene, templates=None):
    templates = load_templates() if templates is None else templates
    check_forbidden(templates)
    check_forbidden(record["text"])
    group = record["template_group"]
    if "split" in record:
        split, diagnostic = record["split"], record["diagnostic_template_A"]
        allowed = ((split in ("train", "val") and group == "A" and not diagnostic and record["variant"] in range(3))
                   or (split == "test" and record["variant"] == 0
                       and ((group == "B" and not diagnostic) or (group == "A" and diagnostic))))
        if not allowed:
            raise P0ContractError("Template group/split contract violated")
    expected = list(_expected(labels))
    if len(record["sentences"]) != len(expected):
        raise P0ContractError("Sentence gating/count differs from labels")
    for sentence, (kind, gid, prefix, gates) in zip(record["sentences"], expected):
        if sentence["type"] != kind or sentence["group_id"] != gid:
            raise P0ContractError("Sentence order/type/group differs from labels")
        if sentence["gate_refs"] != gates:
            raise P0ContractError(f"Gate provenance differs: {gid}/{kind}")
        tid = sentence["template_id"]
        if tid not in (group + "1", group + "2"):
            raise P0ContractError("Sentence template group mismatch")
        template = templates[kind][tid]
        values, refs = _source_bindings(labels, gid, prefix)
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
        if prefix:
            fields.add("subj")
        wanted_values = {k: values[k] for k in sorted(fields)}
        wanted_refs = {k: refs[k] for k in sorted(fields)}
        # Resolve every emitted pointer independently, including count sources.
        for pointers in sentence["fact_refs"].values():
            for path in pointers:
                resolve_pointer(labels, path)
        if sentence["fact_refs"] != wanted_refs or sentence["values"] != wanted_values:
            raise P0ContractError(f"Fact binding mismatch: {gid}/{kind}")
        text = (wanted_values["subj"] if prefix else "") + template.format(**wanted_values)
        if sentence["text"] != text:
            raise P0ContractError(f"Sentence text differs from its source values: {gid}/{kind}")
        if gid is not None:
            target = labels["task_groups"][gid]["assigned"]["target"]
            if not any(e["type"] == "facility" and e["id"] == target for e in public_scene["entities"]):
                raise P0ContractError("Bound facility is absent from public scene")
    if record["text"] != "".join(s["text"] for s in record["sentences"]):
        raise P0ContractError("Description concatenation differs from sentences")
    return True
