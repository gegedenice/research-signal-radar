#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jsonschema>=4.23,<5",
# ]
# ///
"""Validate the common research-signal contract against dummy detector fixtures."""

from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def semantic_errors(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    observations = {item["observation_id"]: item for item in bundle["observations"]}
    manifests = {item["manifest_id"]: item for item in bundle["manifests"]}
    signals = {item["signal_id"]: item for item in bundle["signals"]}

    envelope_keys = [set(item) for item in bundle["signals"]]
    if envelope_keys and any(keys != envelope_keys[0] for keys in envelope_keys[1:]):
        errors.append("signal envelope keys differ between detectors")

    for observation in bundle["observations"]:
        observation_id = observation["observation_id"]
        manifest = manifests.get(observation["source"]["manifest_id"])
        if manifest is None:
            errors.append(f"{observation_id}: unresolved source manifest")
            continue
        if observation["observed_at"] != manifest["observed_at"]:
            errors.append(f"{observation_id}: observation vintage differs from source manifest")
        if observation["inclusion"]["universe_id"] != manifest["universe_id"]:
            errors.append(f"{observation_id}: universe differs from source manifest")

    for signal in bundle["signals"]:
        signal_id = signal["signal_id"]
        detector_type = signal["detector"]["type"]
        detected_at = parse_dt(signal["detected_at"])

        if signal["payload"].get("payload_schema") != detector_type:
            errors.append(f"{signal_id}: payload schema does not match detector type")

        if signal["provenance"]["query_manifest_id"] not in manifests:
            errors.append(f"{signal_id}: unresolved query manifest")

        current_end = datetime.fromisoformat(
            signal["analysis_context"]["current_window"]["end"] + "T23:59:59+00:00"
        )
        if current_end > detected_at:
            errors.append(f"{signal_id}: current window ends after cutoff")

        for evidence in signal["evidence"]:
            if parse_dt(evidence["observed_at"]) > detected_at:
                errors.append(f"{signal_id}: evidence {evidence['evidence_id']} leaks future data")
            locator = evidence["locator"]
            if locator["kind"] == "observation" and locator["id"] not in observations:
                errors.append(f"{signal_id}: unresolved observation {locator['id']}")

        subject = signal["subject"]
        if detector_type == "topic_momentum":
            topic_id = subject["id"]
            supporting = [
                observations[item["locator"]["id"]]
                for item in signal["evidence"]
                if item["locator"]["kind"] == "observation"
                and item["locator"]["id"] in observations
            ]
            if not any(
                work["primary_topic"] is not None
                and work["primary_topic"]["id"] == topic_id
                for work in supporting
            ):
                errors.append(f"{signal_id}: no supporting observation has the signalled topic")

        elif detector_type == "citation_acceleration":
            snapshots = sorted(
                (
                    parse_dt(work["observed_at"]),
                    work["citation_snapshot"]["cited_by_count"],
                )
                for work in bundle["observations"]
                if work["work_id"] == subject["id"]
                and parse_dt(work["observed_at"]) <= detected_at
            )
            if len(snapshots) < 2:
                errors.append(f"{signal_id}: fewer than two citation snapshots")
            elif snapshots[-1][1] < snapshots[0][1]:
                errors.append(f"{signal_id}: citation count decreases between snapshots")

        elif detector_type == "actor_collaboration_novelty":
            members = set(subject["member_ids"])
            if len(members) != 2:
                errors.append(f"{signal_id}: collaboration subject must contain two members")
            coauthored = False
            for work in bundle["observations"]:
                if parse_dt(work["observed_at"]) > detected_at:
                    continue
                author_ids = {item["author_id"] for item in work["authorships"]}
                if members.issubset(author_ids):
                    coauthored = True
                    break
            if not coauthored:
                errors.append(f"{signal_id}: collaboration members never co-occur")

    for result in bundle["backtests"]:
        signal = signals.get(result["signal_id"])
        if signal is None:
            errors.append(f"{result['backtest_id']}: unresolved signal")
            continue
        if result["cutoff"] != signal["detected_at"]:
            errors.append(f"{result['backtest_id']}: cutoff differs from signal detected_at")
        if datetime.fromisoformat(result["horizon_end"]).date() <= parse_dt(result["cutoff"]).date():
            errors.append(f"{result['backtest_id']}: horizon is not prospective")

    return errors


def schema_errors(validator: Draft202012Validator, instance: dict[str, Any]) -> list[str]:
    return [error.message for error in validator.iter_errors(instance)]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_dummy_compatibility.py SCHEMA FIXTURES", file=sys.stderr)
        return 2

    schema = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    bundle = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    tests: list[dict[str, Any]] = []

    base_schema_errors = schema_errors(validator, bundle)
    base_semantic_errors = semantic_errors(bundle)
    tests.append(
        {
            "test": "valid_three_detector_bundle",
            "expected": "accept",
            "passed": not base_schema_errors and not base_semantic_errors,
            "errors": base_schema_errors + base_semantic_errors,
        }
    )

    cases: list[tuple[str, dict[str, Any], str]] = []

    bad_confidence = copy.deepcopy(bundle)
    bad_confidence["signals"][0]["confidence"]["score"] = 1.5
    cases.append(("reject_confidence_above_one", bad_confidence, "schema"))

    leaked_field = copy.deepcopy(bundle)
    leaked_field["signals"][0]["topic_specific_metric"] = 42
    cases.append(("reject_detector_field_outside_payload", leaked_field, "schema"))

    future_evidence = copy.deepcopy(bundle)
    future_evidence["signals"][0]["evidence"][0]["observed_at"] = "2025-07-01T00:00:00Z"
    cases.append(("reject_future_evidence", future_evidence, "semantic"))

    wrong_manifest_vintage = copy.deepcopy(bundle)
    wrong_manifest_vintage["observations"][2]["source"]["manifest_id"] = (
        "qm-openalex-mines-2025h1-v1"
    )
    cases.append(("reject_observation_manifest_vintage_mismatch", wrong_manifest_vintage, "semantic"))

    missing_topic = copy.deepcopy(bundle)
    for observation in missing_topic["observations"]:
        if observation["observation_id"].startswith("obs-W100"):
            observation["primary_topic"] = None
    cases.append(("reject_topic_signal_without_support", missing_topic, "semantic"))

    for name, instance, layer in cases:
        errors = schema_errors(validator, instance)
        if layer == "semantic" and not errors:
            errors = semantic_errors(instance)
        tests.append(
            {
                "test": name,
                "expected": "reject",
                "passed": bool(errors),
                "errors": errors,
            }
        )

    by_detector: dict[str, int] = defaultdict(int)
    for signal in bundle["signals"]:
        by_detector[signal["detector"]["type"]] += 1

    report = {
        "contract_version": bundle["schema_version"],
        "detectors_exercised": dict(sorted(by_detector.items())),
        "observation_count": len(bundle["observations"]),
        "signal_count": len(bundle["signals"]),
        "backtest_count": len(bundle["backtests"]),
        "tests": tests,
        "overall": "PASS" if all(item["passed"] for item in tests) else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
