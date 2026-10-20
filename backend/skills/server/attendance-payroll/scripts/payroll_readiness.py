#!/usr/bin/env python3
"""Validate a Payroll historical-salary readiness response against current Skill data.

This script never calls Payroll. The caller must supply a fresh response from the
read-only check_historical_salary_readiness MCP tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


RULES_VERSION = "W03.6"
STATUSES = {"COVERED", "MISSING_HISTORY", "AMBIGUOUS_HISTORY", "UNKNOWN"}
MAX_PEOPLE = 500
COUNT_FIELDS = {
    "COVERED": "covered_count",
    "MISSING_HISTORY": "missing_count",
    "AMBIGUOUS_HISTORY": "ambiguous_count",
    "UNKNOWN": "unknown_count",
}


class ReadinessError(ValueError):
    """Input is incomplete, stale, or inconsistent with the Payroll contract."""


def _read(path: str | Path) -> tuple[object, bytes]:
    raw = Path(path).read_bytes()
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"JSON_INVALID:{Path(path).name}") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha(payload)


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ReadinessError(f"{label}_MUST_BE_OBJECT")
    return value


def _person_id(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ReadinessError(f"{label}_INVALID")
    return value


def _confirmed_identity(row: dict) -> int:
    """Accept only the current person_matches.py auto or user-confirmed row forms."""
    pid = _person_id(row.get("payroll_person_id"), "PAYROLL_PERSON_ID")
    if row.get("match_method") == "active_roster_unique":
        _person_id(row.get("roster_id"), "ROSTER_ID")
        return pid
    confirmation = row.get("user_confirmation")
    if isinstance(confirmation, dict) and confirmation.get("source") == "user" and isinstance(
        confirmation.get("note"), str
    ) and confirmation["note"].strip():
        candidates = row.get("candidates")
        if isinstance(candidates, list):
            selected = [item for item in candidates if isinstance(item, dict) and item.get("payroll_person_id") == pid]
            if len(selected) == 1 and selected[0].get("roster_active") is True:
                _person_id(selected[0].get("roster_id"), "ROSTER_ID")
                return pid
    raise ReadinessError("MATCHED_IDENTITY_PROVENANCE_INVALID")


def _month(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ReadinessError("MONTH_INVALID")
    return value


def _current_inputs(attendance_path: str, matches_path: str, month: str,
                    record_ids_path: str | None = None, allow_empty: bool = False) -> dict:
    attendance, attendance_raw = _read(attendance_path)
    matches_data, matches_raw = _read(matches_path)
    attendance = _object(attendance, "ATTENDANCE")
    matches_data = _object(matches_data, "PERSON_MATCHES")
    if attendance.get("schema_version") != 1 or not isinstance(attendance.get("people"), list):
        raise ReadinessError("ATTENDANCE_SCHEMA_INVALID")
    month = _month(month)
    if _month(attendance.get("month")) != month:
        raise ReadinessError("ATTENDANCE_MONTH_MISMATCH")
    rows = matches_data.get("matches")
    if matches_data.get("schema_version") != 1 or not isinstance(rows, list):
        raise ReadinessError("PERSON_MATCHES_SCHEMA_INVALID")
    attendance_sha256 = _sha(attendance_raw)
    if matches_data.get("attendance_sha256") != attendance_sha256:
        raise ReadinessError("PERSON_MATCHES_ATTENDANCE_STALE")

    attendance_by_id = {}
    for index, raw in enumerate(attendance["people"]):
        person = _object(raw, f"ATTENDANCE_PERSON_{index}")
        record_id = person.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip() or record_id in attendance_by_id:
            raise ReadinessError("ATTENDANCE_RECORD_ID_INVALID_OR_DUPLICATE")
        attendance_by_id[record_id] = person

    match_by_id = {}
    for index, raw in enumerate(rows):
        row = _object(raw, f"MATCH_{index}")
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or record_id not in attendance_by_id or record_id in match_by_id:
            raise ReadinessError("MATCH_RECORD_ID_UNKNOWN_OR_DUPLICATE")
        match_status = row.get("status")
        if not isinstance(match_status, str) or match_status not in {
            "matched", "ambiguous", "unmatched", "pending_confirmation"
        }:
            raise ReadinessError("MATCH_STATUS_INVALID")
        match_by_id[record_id] = row
    if set(match_by_id) != set(attendance_by_id):
        raise ReadinessError("MATCH_COVERAGE_INCOMPLETE")

    matched: dict[str, int] = {}
    used_ids: dict[int, str] = {}
    for record_id, row in match_by_id.items():
        if row.get("status") != "matched":
            continue
        pid = _confirmed_identity(row)
        if pid in used_ids and used_ids[pid] != record_id:
            raise ReadinessError("PAYROLL_PERSON_ID_MAPPED_TO_MULTIPLE_RECORDS")
        used_ids[pid] = record_id
        matched[record_id] = pid

    selected_ids = set(matched)
    scope_source = "all_matched"
    if record_ids_path:
        requested, _ = _read(record_ids_path)
        if not isinstance(requested, list) or any(not isinstance(x, str) for x in requested):
            raise ReadinessError("RECORD_IDS_MUST_BE_STRING_ARRAY")
        if len(requested) != len(set(requested)):
            raise ReadinessError("RECORD_ID_DUPLICATE")
        selected_ids = set(requested)
        if not selected_ids or not selected_ids.issubset(matched):
            raise ReadinessError("SELECTED_RECORDS_NOT_ALL_RELIABLY_MATCHED")
        scope_source = "explicit_record_ids"
    if not selected_ids and not allow_empty:
        raise ReadinessError("NO_RELIABLY_MATCHED_PAYROLL_PERSON_IDS")

    selected = sorted((matched[record_id], record_id) for record_id in selected_ids)
    person_ids = [pid for pid, _ in selected]
    if len(person_ids) != len(set(person_ids)):
        raise ReadinessError("PAYROLL_PERSON_ID_DUPLICATE")
    if len(person_ids) > MAX_PEOPLE:
        raise ReadinessError("MCP_MAX_PEOPLE_EXCEEDED")
    return {
        "month": _month(month),
        "attendance": attendance,
        "attendance_raw": attendance_raw,
        "matches": matches_data,
        "matches_raw": matches_raw,
        "attendance_sha256": attendance_sha256,
        "person_matches_sha256": _sha(matches_raw),
        "matched": matched,
        "selected_record_ids": sorted(selected_ids),
        "payroll_person_ids": person_ids,
        "scope_source": scope_source,
        "identity_not_in_scope": [
            {"record_id": rid, "name": attendance_by_id[rid].get("name"), "status": match_by_id[rid].get("status")}
            for rid in sorted(attendance_by_id) if match_by_id[rid].get("status") != "matched"
        ],
        "scope_excluded_records": [
            {"record_id": rid, "name": attendance_by_id[rid].get("name")}
            for rid in sorted(matched) if rid not in selected_ids
        ],
    }


def _validate_response(response: object, month: str, person_ids: list[int]) -> tuple[dict, dict[str, int]]:
    response = _object(response, "PAYROLL_RESPONSE")
    if response.get("payroll_month") != month:
        raise ReadinessError("RESPONSE_MONTH_MISMATCH")
    items = response.get("items")
    if not isinstance(items, list):
        raise ReadinessError("RESPONSE_ITEMS_INVALID")
    total = response.get("total_count")
    if isinstance(total, bool) or not isinstance(total, int) or total != len(person_ids) or total != len(items):
        raise ReadinessError("RESPONSE_TOTAL_COUNT_MISMATCH")

    requested = set(person_ids)
    by_id = {}
    counts = {status: 0 for status in STATUSES}
    normalized_items = []
    for index, raw in enumerate(items):
        item = _object(raw, f"RESPONSE_ITEM_{index}")
        pid = _person_id(item.get("payroll_person_id"), "RESPONSE_PERSON_ID")
        if pid not in requested or pid in by_id:
            raise ReadinessError("RESPONSE_PERSON_ID_EXTRA_OR_DUPLICATE")
        status = item.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise ReadinessError("RESPONSE_STATUS_INVALID")
        source_month = item.get("source_month")
        if status == "COVERED":
            if not isinstance(source_month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", source_month):
                raise ReadinessError("COVERED_SOURCE_MONTH_REQUIRED")
            if source_month > month:
                raise ReadinessError("SOURCE_MONTH_AFTER_TARGET")
        elif source_month is not None:
            raise ReadinessError("NON_COVERED_SOURCE_MONTH_FORBIDDEN")
        reason = item.get("reason_code", "")
        if not isinstance(reason, str):
            raise ReadinessError("REASON_CODE_INVALID")
        by_id[pid] = True
        counts[status] += 1
        normalized_items.append({
            "payroll_person_id": pid,
            "status": status,
            "source_month": source_month,
            "reason_code": reason,
        })
    if set(by_id) != requested:
        raise ReadinessError("RESPONSE_PERSON_ID_MISSING")
    if sum(counts.values()) != total:
        raise ReadinessError("RESPONSE_STATUS_TOTAL_MISMATCH")
    for status, field in COUNT_FIELDS.items():
        value = response.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value != counts[status]:
            raise ReadinessError(f"RESPONSE_{field.upper()}_MISMATCH")
    normalized_response = {
        "payroll_month": month,
        "total_count": total,
        "items": sorted(normalized_items, key=lambda entry: entry["payroll_person_id"]),
    }
    return normalized_response, counts


def _atomic_write(path: str | Path, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def build_report(attendance_path: str, matches_path: str, month: str, response_path: str,
                 record_ids_path: str | None = None) -> dict:
    current = _current_inputs(attendance_path, matches_path, month, record_ids_path)
    response, response_raw = _read(response_path)
    normalized_response, counts = _validate_response(
        response, current["month"], current["payroll_person_ids"]
    )
    items_by_id = {item["payroll_person_id"]: item for item in normalized_response["items"]}
    selected_by_record = {
        record_id: items_by_id[pid]
        for record_id, pid in current["matched"].items()
        if record_id in current["selected_record_ids"]
    }
    names_by_record = {
        person["record_id"]: person.get("name")
        for person in current["attendance"]["people"] if isinstance(person, dict)
    }
    details = []
    for record_id in current["selected_record_ids"]:
        item = selected_by_record[record_id]
        name = names_by_record[record_id]
        if not isinstance(name, str) or not name.strip():
            raise ReadinessError("ATTENDANCE_PERSON_NAME_INVALID")
        details.append({
            "record_id": record_id,
            "name": name,
            **item,
        })
    report = {
        "schema_version": 1,
        "rules_version": RULES_VERSION,
        "status": "COVERAGE_CHECKED",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payroll_month": current["month"],
        "attendance_sha256": current["attendance_sha256"],
        "person_matches_sha256": current["person_matches_sha256"],
        "requested_payroll_person_ids": current["payroll_person_ids"],
        "selected_record_ids": current["selected_record_ids"],
        "scope_source": current["scope_source"],
        "payroll_response_sha256": _sha(response_raw),
        "payroll_response_digest_scope": "raw_response_file_digest_not_reverified",
        "counts": {
            "requested": len(current["payroll_person_ids"]),
            "covered": counts["COVERED"],
            "missing_history": counts["MISSING_HISTORY"],
            "ambiguous_history": counts["AMBIGUOUS_HISTORY"],
            "unknown": counts["UNKNOWN"],
            "identity_not_in_scope": len(current["identity_not_in_scope"]),
            "excluded_by_user_scope": len(current["scope_excluded_records"]),
        },
        "identity_not_in_scope": current["identity_not_in_scope"],
        "scope_excluded_records": current["scope_excluded_records"],
        "items": details,
        "is_authorization": False,
        "is_payroll_receipt": False,
        "is_formal_precheck": False,
        "coverage_does_not_prove_precheck": True,
        "payroll_response_summary": normalized_response,
    }
    report["normalized_response_sha256"] = _canonical_sha(normalized_response)
    return report


def _default_calculable_scope(report: dict) -> dict:
    """Derive a reviewable default scope from reliable identities with COVERED history."""
    eligible = [item for item in report["items"] if item["status"] == "COVERED"]
    eligible.sort(key=lambda item: item["record_id"])
    return {
        "payroll_month": report["payroll_month"],
        "attendance_sha256": report["attendance_sha256"],
        "person_matches_sha256": report["person_matches_sha256"],
        "record_ids": [item["record_id"] for item in eligible],
        "payroll_person_ids": [item["payroll_person_id"] for item in eligible],
        "people": [
            {"record_id": item["record_id"], "name": item["name"],
             "payroll_person_id": item["payroll_person_id"]}
            for item in eligible
        ],
        "count": len(eligible),
    }


def write_unavailable(attendance_path: str, matches_path: str, month: str, output_path: str,
                      reason: str) -> dict:
    if not isinstance(reason, str) or not reason.strip():
        raise ReadinessError("UNAVAILABLE_REASON_REQUIRED")
    # Failure-state creation deliberately does not read attendance or identity files:
    # those may be the reason the check failed.
    result = {
        "schema_version": 1,
        "rules_version": RULES_VERSION,
        "status": "UNAVAILABLE",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payroll_month": (
            month if isinstance(month, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) else None
        ),
        "reason": reason.strip(),
        "business_inputs_revalidated": False,
        "is_authorization": False,
        "is_payroll_receipt": False,
        "is_formal_precheck": False,
    }
    _atomic_write(output_path, result)
    return result


def report_status(report_path: str, attendance_path: str, matches_path: str, month: str,
                  record_ids_path: str | None = None) -> dict:
    try:
        report, _ = _read(report_path)
        report = _object(report, "READINESS_REPORT")
    except (ReadinessError, OSError):
        return {"ok": False, "status": "READINESS_REPORT_INVALID"}
    if report.get("status") == "UNAVAILABLE":
        return {"ok": False, "status": "UNAVAILABLE"}
    try:
        current = _current_inputs(attendance_path, matches_path, month, record_ids_path, allow_empty=True)
    except ReadinessError as exc:
        if str(exc) == "PERSON_MATCHES_ATTENDANCE_STALE":
            return {"ok": False, "status": "READINESS_STALE"}
        return {"ok": False, "status": "READINESS_CHECK_BLOCKED"}
    except OSError:
        return {"ok": False, "status": "READINESS_CHECK_BLOCKED"}
    if report.get("schema_version") != 1 or report.get("rules_version") != RULES_VERSION:
        return {"ok": False, "status": "READINESS_REPORT_INVALID"}
    if report.get("status") != "COVERAGE_CHECKED":
        return {"ok": False, "status": "READINESS_REPORT_INVALID"}
    expected = {
        "payroll_month": current["month"],
        "attendance_sha256": current["attendance_sha256"],
        "person_matches_sha256": current["person_matches_sha256"],
        "requested_payroll_person_ids": current["payroll_person_ids"],
        "selected_record_ids": current["selected_record_ids"],
    }
    requested_ids = report.get("requested_payroll_person_ids")
    if not isinstance(requested_ids, list) or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in requested_ids
    ):
        return {"ok": False, "status": "READINESS_REPORT_INVALID"}
    if any(report.get(key) != value for key, value in expected.items()):
        return {"ok": False, "status": "READINESS_STALE"}

    def invalid() -> dict:
        return {"ok": False, "status": "READINESS_REPORT_INVALID"}

    sha_fields = (
        "attendance_sha256", "person_matches_sha256", "payroll_response_sha256", "normalized_response_sha256"
    )
    if any(
        not isinstance(report.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", report[key])
        for key in sha_fields
    ):
        return invalid()
    if report.get("payroll_response_digest_scope") != "raw_response_file_digest_not_reverified":
        return invalid()
    try:
        datetime.fromisoformat(report.get("checked_at", "").replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return invalid()
    scope_source = report.get("scope_source")
    if not isinstance(scope_source, str) or scope_source not in {"all_matched", "explicit_record_ids"}:
        return invalid()
    if any(report.get(key) is not value for key, value in {
        "is_authorization": False, "is_payroll_receipt": False,
        "is_formal_precheck": False, "coverage_does_not_prove_precheck": True,
    }.items()):
        return invalid()

    selected_ids = current["selected_record_ids"]
    if report.get("selected_record_ids") != selected_ids:
        return {"ok": False, "status": "READINESS_STALE"}
    attendance_by_id = {person["record_id"]: person for person in current["attendance"]["people"]}
    expected_items = []
    seen_ids: set[int] = set()
    state_counts = {"COVERED": 0, "MISSING_HISTORY": 0, "AMBIGUOUS_HISTORY": 0, "UNKNOWN": 0}
    items = report.get("items")
    if not isinstance(items, list) or len(items) != len(selected_ids):
        return invalid()
    for record_id, item in zip(selected_ids, items, strict=True):
        if (
            not isinstance(item, dict)
            or set(item) != {"record_id", "name", "payroll_person_id", "status", "source_month", "reason_code"}
            or item.get("record_id") != record_id
        ):
            return invalid()
        pid = current["matched"].get(record_id)
        try:
            item_pid = _person_id(item.get("payroll_person_id"), "REPORT_PERSON_ID")
        except ReadinessError:
            return invalid()
        if pid is None or item_pid != pid or pid in seen_ids:
            return invalid()
        person_name = attendance_by_id[record_id].get("name")
        if not isinstance(person_name, str) or item.get("name") != person_name:
            return invalid()
        status_value = item.get("status")
        if not isinstance(status_value, str) or status_value not in state_counts:
            return invalid()
        source_month = item.get("source_month")
        if status_value == "COVERED":
            try:
                source_month = _month(source_month)
            except ReadinessError:
                return invalid()
            if source_month > current["month"]:
                return invalid()
        elif source_month is not None:
            return invalid()
        reason = item.get("reason_code")
        if not isinstance(reason, str):
            return invalid()
        state_counts[status_value] += 1
        seen_ids.add(pid)
        expected_items.append({
            "record_id": record_id, "name": person_name, "payroll_person_id": pid,
            "status": status_value, "source_month": source_month, "reason_code": reason,
        })

    expected_counts = {
        "requested": len(current["payroll_person_ids"]), "covered": state_counts["COVERED"],
        "missing_history": state_counts["MISSING_HISTORY"], "ambiguous_history": state_counts["AMBIGUOUS_HISTORY"],
        "unknown": state_counts["UNKNOWN"], "identity_not_in_scope": len(current["identity_not_in_scope"]),
        "excluded_by_user_scope": len(current["scope_excluded_records"]),
    }
    reported_counts = report.get("counts")
    if not isinstance(reported_counts, dict) or set(reported_counts) != set(expected_counts) or any(
        isinstance(value, bool) or not isinstance(value, int) for value in reported_counts.values()
    ) or reported_counts != expected_counts:
        return invalid()
    if report.get("identity_not_in_scope") != current["identity_not_in_scope"]:
        return invalid()
    if report.get("scope_excluded_records") != current["scope_excluded_records"]:
        return invalid()
    expected_summary = {
        "payroll_month": current["month"],
        "total_count": len(current["payroll_person_ids"]),
        "items": sorted([
            {key: item[key] for key in ("payroll_person_id", "status", "source_month", "reason_code")}
            for item in expected_items
        ], key=lambda entry: entry["payroll_person_id"]),
    }
    summary = report.get("payroll_response_summary")
    if summary != expected_summary or _canonical_sha(summary) != report["normalized_response_sha256"]:
        return invalid()
    if sum(state_counts.values()) != expected_counts["requested"]:
        return invalid()
    return {
        "ok": True, "status": "COVERAGE_CHECKED", "counts": expected_counts,
        "payroll_response_sha256_verified": False,
        "default_calculable_scope": _default_calculable_scope(report),
    }


def _emit_error(exc: Exception) -> int:
    print(json.dumps({"ok": False, "status": "READINESS_CHECK_BLOCKED", "error": str(exc)}, ensure_ascii=False))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request", help="emit exact MCP request from current matched identities")
    request.add_argument("--attendance", required=True)
    request.add_argument("--matches", required=True)
    request.add_argument("--month", required=True)
    request.add_argument("--record-ids", help="JSON string array for an explicitly user-approved exact scope")
    check = commands.add_parser("check", help="validate a fresh MCP response and write the internal report")
    check.add_argument("--attendance", required=True)
    check.add_argument("--matches", required=True)
    check.add_argument("--month", required=True)
    check.add_argument("--response", required=True)
    check.add_argument("--record-ids", help="JSON string array for a user-approved exact scope")
    check.add_argument("--output", required=True)
    unavailable = commands.add_parser("unavailable", help="record that the read-only MCP check could not be completed")
    unavailable.add_argument("--attendance", required=True)
    unavailable.add_argument("--matches", required=True)
    unavailable.add_argument("--month", required=True)
    unavailable.add_argument("--reason", required=True)
    unavailable.add_argument("--output", required=True)
    status = commands.add_parser("status", help="check whether a report still binds current inputs and scope")
    status.add_argument("--attendance", required=True)
    status.add_argument("--matches", required=True)
    status.add_argument("--month", required=True)
    status.add_argument("--report", required=True)
    status.add_argument("--record-ids")
    args = parser.parse_args(argv)
    try:
        if args.command == "request":
            current = _current_inputs(args.attendance, args.matches, args.month, args.record_ids, allow_empty=True)
            print(json.dumps({
                "status": "IDENTITY_PENDING" if not current["payroll_person_ids"] else "REQUEST_READY",
                "mcp_request": None if not current["payroll_person_ids"] else {
                    "payroll_month": current["month"], "payroll_person_ids": current["payroll_person_ids"]},
                "identity_not_in_scope": current["identity_not_in_scope"],
                "scope_excluded_records": current["scope_excluded_records"],
                "is_authorization": False,
            }, ensure_ascii=False, sort_keys=True))
        elif args.command == "check":
            protected = {Path(args.attendance).resolve(), Path(args.matches).resolve(), Path(args.response).resolve()}
            if Path(args.output).resolve() in protected:
                raise ReadinessError("OUTPUT_CANNOT_OVERWRITE_INPUT")
            try:
                report = build_report(args.attendance, args.matches, args.month, args.response, args.record_ids)
                _atomic_write(args.output, report)
            except (ReadinessError, OSError) as check_error:
                try:
                    write_unavailable(
                        args.attendance, args.matches, args.month, args.output,
                        f"CHECK_FAILED:{type(check_error).__name__}",
                    )
                except (ReadinessError, OSError) as write_error:
                    raise ReadinessError(f"UNAVAILABLE_STATE_WRITE_FAILED:{type(write_error).__name__}") from write_error
                raise
            print(json.dumps({"ok": True, "status": report["status"], "path": args.output,
                              "counts": report["counts"],
                              "default_calculable_scope": _default_calculable_scope(report),
                              "is_authorization": False}, ensure_ascii=False))
        elif args.command == "unavailable":
            if Path(args.output).resolve() in {Path(args.attendance).resolve(), Path(args.matches).resolve()}:
                raise ReadinessError("OUTPUT_CANNOT_OVERWRITE_INPUT")
            report = write_unavailable(args.attendance, args.matches, args.month, args.output, args.reason)
            print(json.dumps({"ok": True, "status": report["status"], "path": args.output,
                              "is_authorization": False}, ensure_ascii=False))
        else:
            print(json.dumps(report_status(args.report, args.attendance, args.matches, args.month, args.record_ids),
                             ensure_ascii=False))
            return 0
        return 0
    except (ReadinessError, OSError) as exc:
        return _emit_error(exc)


if __name__ == "__main__":
    sys.exit(main())
