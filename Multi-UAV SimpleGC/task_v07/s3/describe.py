"""Exact template rendering; no free-form text generation."""
import hashlib
import random
import string

from ._common import P0ContractError
from .verify import check_forbidden, load_templates

INTENTS = {"transit": "过境", "reconnaissance": "侦察", "monitoring": "监视",
           "feint": "佯动", "penetration": "突防"}


def _selection(facts):
    yield "overview", None, False
    for group in facts["groups"]:
        first = True
        if group["entered_warning_all"]:
            suffix = {"same_direction": "same", "multi_direction": "multi"}.get(group["approach_class"], "neutral")
            yield "approach_" + suffix, group, False
            first = False
        if group["coordination"] in ("synchronous", "sequential"):
            yield "coord_sync" if group["coordination"] == "synchronous" else "coord_seq", group, first
            first = False
        if group["group_status"] == "success":
            yield "role_" + group["execution_method"], group, first
            first = False
        if group["exit_state"] in ("all_outside", "all_inside"):
            yield "exit_out" if group["exit_state"] == "all_outside" else "exit_in", group, first
    yield "intent_conforms" if facts["cluster_status"] == "success" else "intent_insufficient", None, False


def _bindings(facts, group, prefix):
    k = facts["n_groups"]
    values = {"n": facts["n_agents"],
              "grouping": "作为一个编组行动" if k == 1 else f"分为{k}个编组",
              "intent": INTENTS[facts["cluster_intent"]]}
    refs = {"n": ["/agents"], "grouping": ["/task_groups"],
            "intent": ["/cluster/assigned/intent"]}
    if group is not None:
        gp = "/task_groups/" + group["group_id"]
        values.update(subj="该编组" if k == 1 else f"第{group['index']}编组（{group['n_members']}架）",
                      subj2="" if k == 1 or prefix else "该编组",
                      f=group["facility_no"], dir=group["from_sector"],
                      cov=group["coverage_pct"], dwell=group["dwell_s"], B=group["batch_count"])
        refs.update(subj=["/task_groups", gp + "/observed/members"],
                    subj2=["/task_groups"], f=group["fact_refs"]["facility_no"],
                    dir=group["fact_refs"]["from_sector"], cov=group["fact_refs"]["coverage_pct"],
                    dwell=group["fact_refs"]["dwell_s"], B=group["fact_refs"]["batch_count"])
    return values, refs


def _gate_refs(kind, group):
    if group is None:
        return ["/cluster/result/status"] if kind.startswith("intent") else []
    gp = "/task_groups/" + group["group_id"]
    if kind.startswith("approach"):
        return group["fact_refs"]["entered_warning_all"] + group["fact_refs"]["approach_class"]
    if kind.startswith("role"):
        return [gp + "/result/status", gp + "/assigned/execution_method"]
    if kind.startswith("coord"):
        return [gp + "/observed/coordination/classification"]
    return group["fact_refs"]["exit_state"]


def render_description(facts, episode_key, template_group, variant=0, templates=None):
    templates = load_templates() if templates is None else templates
    check_forbidden(templates)
    if template_group not in ("A", "B"):
        raise ValueError("Template group must be A or B")
    seed = int(hashlib.sha256(f"{episode_key}:{variant}".encode()).hexdigest(), 16)
    rng = random.Random(seed)
    sentences = []
    for kind, group, prefix in _selection(facts):
        tid = template_group + str(rng.choice((1, 2)))
        template = templates[kind][tid]
        values, refs = _bindings(facts, group, prefix)
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
        if prefix:
            fields.add("subj")
        values = {name: values[name] for name in sorted(fields)}
        refs = {name: refs[name] for name in sorted(fields)}
        text = (values["subj"] if prefix else "") + template.format(**values)
        sentences.append({"type": kind, "template_id": tid, "text": text, "values": values,
                          "fact_refs": refs, "gate_refs": _gate_refs(kind, group),
                          "group_id": group["group_id"] if group else None})
    text = "".join(s["text"] for s in sentences)
    check_forbidden(text)
    return {"episode_key": episode_key, "template_group": template_group, "variant": variant,
            "diagnostic_template_A": False, "text": text, "sentences": sentences}


def description_variants(facts, episode_key, split, templates=None):
    if split in ("train", "val"):
        choices = [("A", i, False) for i in range(3)]
    elif split == "test":
        choices = [("B", 0, False), ("A", 0, True)]
    else:
        raise P0ContractError(f"Unknown split: {split}")
    result = []
    for group, variant, diagnostic in choices:
        record = render_description(facts, episode_key, group, variant, templates)
        record.update(split=split, diagnostic_template_A=diagnostic)
        result.append(record)
    return result
