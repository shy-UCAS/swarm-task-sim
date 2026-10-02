"""V3 preflight evidence. Read parameters through Vehicle's single RX inbox.

No parameter is written. The accepted WP-S evidence chain is verified before
launch; a changed binary, template or unexplained readback requires a new GO.
"""

import hashlib
import json
import math
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROVENANCE_VERSION = "v3_preflight_provenance_v1"
PARAMETER_COMPARISON_VERSION = "wp_s_parameter_comparison_v2"
STAT_RESET_EPOCH = datetime(2016, 1, 1, tzinfo=timezone.utc)
STAT_RESET_TOLERANCE_S = 300.0
FRESH_INSTANCE_PARAMETERS = {"STAT_BOOTCNT": 1.0, "STAT_FLTTIME": 0.0, "STAT_RUNTIME": 0.0}
PROJECT = Path(__file__).resolve().parents[1]
INSTANCE_PARAMETERS = {
    "SYSID_THISMAV": "per-instance system ID supplied by SITLProcesses",
    "COMPASS_DEC": "automatic magnetic declination depends on the simulated home location",
    "SIM_PLD_LAT": "simulated precision-landing reference initialized from home latitude",
    "SIM_PLD_LON": "simulated precision-landing reference initialized from home longitude",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def binary_identity(binary):
    content = Path(binary).read_bytes()
    matches = list(re.finditer(rb"ArduCopter V[0-9][\x20-\x7e]*", content))
    versions = {m.group().decode("ascii") for m in matches}
    if len(versions) != 1:
        raise ValueError("cannot identify one binary firmware version; a new WP-S GO is required")
    return dict(sha256=hashlib.sha256(content).hexdigest(), version_string=versions.pop(),
                version_source="binary_embedded_ascii_metadata", offset_bytes=matches[0].start())


def verified_wp_s_baseline(project=PROJECT):
    """Follow confirmation -> original metric hashes -> metadata/parameter hashes."""
    project = Path(project)
    confirmation_path = project / "docs/v04_spike_go_confirmation.json"
    confirmation = _json(confirmation_path)
    if (confirmation.get("milestone") != "WP-S" or confirmation.get("decision") != "GO"
            or confirmation.get("accepted_duplicate_policy") != "exact_duplicate_drop_v1"):
        raise ValueError("a confirmed WP-S GO is required")
    links = list(confirmation.get("evidence", [])) + list(confirmation.get("original_unknown_reports", []))
    if len(confirmation.get("original_unknown_reports", [])) != 2 or not confirmation.get("evidence"):
        raise ValueError("WP-S GO is missing its two-run evidence binding")
    for link in links:
        if digest(project / link["path"]) != link["sha256"]:
            raise ValueError(f"WP-S evidence changed: {link['path']}; a new WP-S GO is required")
    baselines = []
    for link in confirmation["original_unknown_reports"]:
        metrics_path = project / link["path"]
        hashes = _json(metrics_path)["source_sha256"]
        for name in ("metadata.json", "firmware_parameters.json"):
            if digest(metrics_path.parent / name) != hashes[name]:
                raise ValueError(f"WP-S source evidence changed: {name}; a new WP-S GO is required")
        metadata = _json(metrics_path.parent / "metadata.json")
        parameters = _json(metrics_path.parent / "firmware_parameters.json")
        if not parameters or not all(item.get("complete") is True for item in parameters.values()):
            raise ValueError("WP-S parameter evidence is incomplete")
        baselines.append(dict(run=metrics_path.parent.name, firmware=metadata["binary_firmware"],
                              parameters_sha256=metadata["parameters_sha256"], agents=parameters))
    fingerprint = {(item["firmware"]["sha256"], item["firmware"]["version_string"], item["parameters_sha256"])
                   for item in baselines}
    if len(fingerprint) != 1:
        raise ValueError("WP-S runs have different firmware/template fingerprints")
    return dict(confirmation_path=str(confirmation_path), confirmation_sha256=digest(confirmation_path),
                baselines=baselines)


def verify_preflight_files(binary, parameters, project=PROJECT):
    baseline = verified_wp_s_baseline(project)
    actual = dict(firmware=binary_identity(binary), parameters_sha256=digest(parameters))
    reference = baseline["baselines"][0]
    if (actual["firmware"]["sha256"] != reference["firmware"]["sha256"]
            or actual["firmware"]["version_string"] != reference["firmware"]["version_string"]
            or actual["parameters_sha256"] != reference["parameters_sha256"]):
        raise ValueError("firmware or parameter template differs from confirmed WP-S fingerprint; a new WP-S GO is required")
    return dict(version=PROVENANCE_VERSION, parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
                status="files_verified", actual=actual,
                confirmation_sha256=baseline["confirmation_sha256"], baseline=baseline)


def check_stat_reset(raw_value, run_started_utc):
    """Check the read-only startup timestamp, retaining evidence on rejection."""
    result = dict(raw_value=raw_value, epoch_utc=STAT_RESET_EPOCH.isoformat(),
                  converted_utc=None, run_started_utc=run_started_utc, delta_s=None,
                  tolerance_s=STAT_RESET_TOLERANCE_S, boundary="inclusive", error=None)
    result["pass"] = False
    try:
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)) or not math.isfinite(raw_value):
            raise ValueError("STAT_RESET must be a finite numeric number of seconds")
        started = datetime.fromisoformat(run_started_utc)
        if started.tzinfo is None or started.utcoffset() is None:
            raise ValueError("run start must include a UTC offset")
        started = started.astimezone(timezone.utc)
        converted = STAT_RESET_EPOCH + timedelta(seconds=raw_value)
        delta = (converted - started).total_seconds()
        result.update(converted_utc=converted.isoformat(), run_started_utc=started.isoformat(), delta_s=delta)
        result["pass"] = abs(delta) <= STAT_RESET_TOLERANCE_S
        if not result["pass"]:
            result["error"] = "STAT_RESET is outside run start +/-300 s"
    except (ValueError, TypeError, OverflowError) as exc:
        result["error"] = str(exc)
    return result


def compare_parameter_readback(evidence, baseline, sysid, *, run_started_utc):
    """V2: full table, fresh EEPROM statistics, and bounded startup timestamp.

    Only STAT_RESET stops using cross-run equality. Navigation/control values,
    unexplained changes, and the existing explicit instance whitelist retain
    their previous treatment. This function never modifies parameter values.
    """
    evidence["parameter_comparison_version"] = PARAMETER_COMPARISON_VERSION
    actual = evidence.get("all_parameters", {})
    reference = baseline["baselines"][0]["agents"]
    reference = reference[sorted(reference)[0]]["all_parameters"]
    changes, unexplained = [], []
    count, received = evidence.get("parameter_count"), evidence.get("received_count")
    complete = (evidence.get("complete") is True and type(count) is int and count > 0
                and type(received) is int and received == count == len(actual) == len(reference)
                and set(actual) == set(reference)
                and evidence.get("missing_indices", []) == []
                and evidence.get("status", "complete") == "complete"
                and all(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
                        for value in actual.values()))
    entries = evidence.get("parameter_entries")
    if entries is not None:
        complete = complete and (isinstance(entries, dict) and set(entries) == {str(i) for i in range(count)}
            and all(isinstance(item, dict) and item.get("name") in actual
                    and item.get("value") == actual[item["name"]] for item in entries.values())
            and len({item.get("name") for item in entries.values()}) == count)
    if not complete:
        unexplained.append("parameter readback incomplete or parameter collection differs")
    timestamp = check_stat_reset(actual.get("STAT_RESET"), run_started_utc)
    if not timestamp["pass"]:
        unexplained.append("STAT_RESET startup timestamp failed plausibility check")
    fresh_instance = {}
    for name, expected in FRESH_INSTANCE_PARAMETERS.items():
        fresh_instance[name] = dict(expected_value=expected, observed_value=actual.get(name),
                                   reason="fresh SITL instance; changed statistics indicate EEPROM reuse")
        fresh_instance[name]["pass"] = actual.get(name) == expected
        if not fresh_instance[name]["pass"]:
            unexplained.append(f"{name} must equal {expected:g} for a fresh SITL instance")
    for name in sorted(set(reference) | set(actual)):
        before, after = reference.get(name), actual.get(name)
        if before == after:
            continue
        explanation = INSTANCE_PARAMETERS.get(name) if name in reference and name in actual else None
        if name == "STAT_RESET" and name in reference and name in actual:
            explanation = "startup timestamp checked against this run start within +/-300 s; not cross-run equality"
        change = dict(name=name, reference_value=before, observed_value=after,
                      explanation=explanation, allowed_instance_difference=explanation is not None)
        changes.append(change)
        if explanation is None:
            unexplained.append(name)
    if actual.get("SYSID_THISMAV") != sysid:
        unexplained.append("SYSID_THISMAV does not match the connected instance")
    evidence["parameter_comparison"] = dict(version=PARAMETER_COMPARISON_VERSION, changes=changes,
        status="evaluated", collection_complete=complete, stat_reset=timestamp, fresh_instance=fresh_instance,
        unchanged_count=sum(actual.get(name) == value for name, value in reference.items()),
        unexplained=unexplained, pass_=not unexplained)
    evidence["parameter_comparison"]["pass"] = evidence["parameter_comparison"].pop("pass_")
    if unexplained:
        raise ValueError("unexplained parameter readback differences require review/new WP-S GO: " + ", ".join(unexplained))


def read_firmware_parameters(client, binary_firmware, evidence=None, timeout=30, retry_interval_s=5,
                             version_timeout_s=10):
    """Bounded complete readback; partial results and every TX survive failures.

    The provided evidence object is updated in place so the owner can persist
    it in its finally block even on cancellation, send error or incomplete RX.
    """
    evidence = {} if evidence is None else evidence
    read_id = uuid.uuid4().hex
    values, count = {}, None
    evidence.update(version=PROVENANCE_VERSION, parameter_comparison_version=PARAMETER_COMPARISON_VERSION,
        agent_id=client.id, sysid=client.sysid,
        read_id=read_id, status="reading", complete=False, started_monotonic_s=time.perf_counter(),
        parameter_count=None, received_count=0, missing_indices=None, requests=[], all_parameters={}, wpnav={})

    def request(kind, purpose, method, args, missing_index=None):
        entry = dict(request_type=kind, purpose=purpose, target_sysid=client.sysid,
                     target_component=client.target_component, missing_index=missing_index,
                     correlation_id=f"{read_id}:{len(evidence['requests'])}",
                     send_before_monotonic_s=time.perf_counter(), send_after_monotonic_s=None,
                     success=False, error=None)
        evidence["requests"].append(entry)
        try:
            client.send(method, *args)
            entry["success"] = True
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry["send_after_monotonic_s"] = time.perf_counter()
            client.event("parameter_request_tx" if kind.startswith("PARAM_") else "firmware_version_request_tx",
                         client.id, **entry)

    def update_progress():
        evidence.update(parameter_count=count, received_count=len(values),
            missing_indices=sorted(set(range(count)) - set(values)) if count is not None else None,
            all_parameters={item["name"]: item["value"] for item in values.values()})
        evidence["wpnav"] = {k: v for k, v in sorted(evidence["all_parameters"].items()) if k.startswith("WPNAV_")}

    try:
        cursor = client.cursor()
        request("COMMAND_LONG", "autopilot_version", "command_long_send",
                (client.sysid, client.target_component, 520, 0, 1, 0, 0, 0, 0, 0, 0))
        try:
            version = client.wait_message(["AUTOPILOT_VERSION"], after=cursor, timeout=min(timeout, version_timeout_s))
        except TimeoutError:
            version = None
        evidence["firmware"] = dict(binary_metadata=binary_firmware,
            autopilot_version_available=version is not None, version_string=binary_firmware["version_string"],
            version_source="binary_embedded_ascii_metadata", runtime_version=None)
        if version is not None:
            evidence["firmware"]["runtime_version"] = version.to_dict()
            evidence["firmware"]["runtime_version_source"] = "AUTOPILOT_VERSION"
            number = int(version.flight_sw_version)
            runtime = (number >> 24, (number >> 16) & 255, (number >> 8) & 255)
            evidence["firmware"]["runtime_version_string"] = ".".join(str(part) for part in runtime) + f" (type {number & 255})"
            embedded = re.match(r"ArduCopter V(\d+)\.(\d+)\.(\d+)", binary_firmware["version_string"])
            if embedded is None or runtime != tuple(int(part) for part in embedded.groups()):
                raise ValueError("AUTOPILOT_VERSION differs from verified binary version; a new WP-S GO is required")
        cursor = client.cursor()
        deadline = time.perf_counter() + timeout
        request("PARAM_REQUEST_LIST", "first", "param_request_list_send", (client.sysid, client.target_component))
        next_retry = time.perf_counter() + retry_interval_s
        while time.perf_counter() < deadline:
            client.check()
            with client.condition:
                batch = [(seq, msg) for seq, kind, msg in client.inbox if seq > cursor and kind == "PARAM_VALUE"]
                cursor = client.sequence
            for _, message in batch:
                reported, index = int(message.param_count), int(message.param_index)
                if reported <= 0 or (count is not None and count != reported):
                    raise ValueError("parameter table count invalid or changed during readback")
                count = reported
                name = message.param_id.decode("ascii") if isinstance(message.param_id, bytes) else message.param_id
                name = name.rstrip("\x00")
                if not 0 <= index < count or not name or not math.isfinite(message.param_value):
                    raise ValueError("invalid parameter index/name/value in readback")
                item = dict(name=name, value=float(message.param_value), type=int(message.param_type))
                if index in values and item != values[index]:
                    raise ValueError("conflicting parameter values during readback")
                values[index] = item
            update_progress()
            if count is not None and len(values) == count:
                if len(evidence["all_parameters"]) != count or not evidence["wpnav"]:
                    raise ValueError("duplicate parameter names or missing WPNAV readback")
                evidence.update(status="complete", complete=True, parameter_entries={str(i): v for i, v in sorted(values.items())})
                client.event("parameter_readback_complete", client.id, read_id=read_id, parameter_count=count,
                             wpnav_count=len(evidence["wpnav"]))
                return evidence
            if time.perf_counter() >= next_retry:
                if count is None:
                    request("PARAM_REQUEST_LIST", "retry", "param_request_list_send", (client.sysid, client.target_component))
                else:
                    for index in evidence["missing_indices"][:100]:
                        request("PARAM_REQUEST_READ", "missing_read", "param_request_read_send",
                                (client.sysid, client.target_component, b"", index), index)
                next_retry = time.perf_counter() + retry_interval_s
            client.cancel.wait(min(.05, max(0, deadline - time.perf_counter())))
        raise TimeoutError(f"{client.id}: incomplete parameter readback ({len(values)}/{count})")
    except BaseException as exc:
        evidence.update(status="failed", error=f"{type(exc).__name__}: {exc}", timed_out=isinstance(exc, TimeoutError))
        raise
    finally:
        update_progress()
        evidence["finished_monotonic_s"] = time.perf_counter()
