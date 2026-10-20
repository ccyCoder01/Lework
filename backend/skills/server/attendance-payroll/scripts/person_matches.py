#!/usr/bin/env python3
"""Build and confirm task-local Payroll identity mappings without business writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import project_binding


CORE_IDENTITY_FIELDS = ("project_name", "company_name", "employee_type")
IDENTITY_FIELDS = (*CORE_IDENTITY_FIELDS, "position")
MATCHING_RULES_VERSION = "W03.9"


def _read(path: str) -> tuple[object, bytes]:
    raw = Path(path).read_bytes()
    return json.loads(raw), raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(path: str, value: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
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


def _obj(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须为对象")
    return value


def _id(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} 必须为正整数")
    return value


def _str(value: object, label: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} 必须为字符串")
    value = value.strip()
    return value or (None if optional else "")


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} 必须为字符串数组")
    return sorted(set(value))


def _canonical_project(value: object, aliases: dict[str, str]) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return aliases.get(normalized, normalized) if normalized else None


def _people(data: object, project_map: dict[str, str]) -> list[dict]:
    data = _obj(data, "attendance.json")
    if data.get("schema_version") != 1 or not isinstance(data.get("people"), list):
        raise ValueError("attendance.json 必须为 schema_version=1 且包含 people 数组")
    result, seen = [], set()
    for i, raw in enumerate(data["people"]):
        person = _obj(raw, f"people[{i}]")
        record_id = _str(person.get("record_id"), f"people[{i}].record_id")
        name = _str(person.get("name"), f"people[{i}].name")
        if not record_id or not name or record_id in seen:
            raise ValueError(f"people[{i}] 的 record_id/name 缺失或 record_id 重复")
        seen.add(record_id)
        project = person.get("project")
        if not isinstance(project, str):
            raise ValueError(f"people[{i}].project 必须为字符串")
        company = _str(person.get("company_name"), f"people[{i}].company_name", True)
        employee_type = person.get("employee_type")
        if employee_type is not None and (
            isinstance(employee_type, bool) or not isinstance(employee_type, int) or not 1 <= employee_type <= 5
        ):
            raise ValueError(f"people[{i}].employee_type 必须为 1–5")
        raw_project = project if project.strip() else None
        if raw_project is None or raw_project not in project_map:
            raise ValueError("考勤来源项目未绑定；请先确认当前任务的全部 Payroll 项目")
        result.append({
            "record_id": record_id,
            "facts": {
                "name": name,
                "source_project_name": raw_project,
                "project_name": project_map[raw_project],
                "company_name": company,
                "employee_type": employee_type,
                "position": _str(person.get("position"), f"people[{i}].position", True),
            },
        })
    return result


def _candidate_request(people: list[dict]) -> dict:
    records = []
    for person in people:
        facts = person["facts"]
        record = {"client_ref": person["record_id"], "name": facts["name"]}
        for field in ("project_name", "company_name", "employee_type"):
            if facts.get(field) is not None:
                record[field] = facts[field]
        # position is deliberately omitted: Payroll treats it as evidence and
        # historical role changes must not filter otherwise valid candidates.
        records.append(record)
    return {"records": records}


def _query_sha(data: dict) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha(canonical)


def _binding_inputs(attendance_path: str, roster_path: str | None, binding_path: str | None) -> tuple[str, str]:
    default_roster, default_binding = project_binding.default_paths(attendance_path)
    return str(roster_path or default_roster), str(binding_path or default_binding)


def candidate_request(attendance_path: str, roster_path: str | None = None, binding_path: str | None = None) -> dict:
    attendance, _ = _read(attendance_path)
    roster_path, binding_path = _binding_inputs(attendance_path, roster_path, binding_path)
    binding = project_binding.validate(attendance_path, roster_path, binding_path)
    return _candidate_request(_people(attendance, binding["project_map"]))


def _verify_query(query_path: str | None, people: list[dict]) -> str:
    expected = _candidate_request(people)
    if query_path is None:
        return _query_sha(expected)
    query, _ = _read(query_path)
    if query != expected:
        raise ValueError("MCP 查询请求与当前考勤及项目别名规则不一致；请重新生成候选请求")
    return _query_sha(query)


def _rosters(data: object) -> dict[int, dict]:
    data = _obj(data, "list_roster 响应")
    if not isinstance(data.get("items"), list):
        raise ValueError("list_roster 响应必须包含 items 数组")
    if "count" in data and data["count"] != len(data["items"]):
        raise ValueError("list_roster count 与 items 数量不一致")
    result = {}
    for i, raw in enumerate(data["items"]):
        row = _obj(raw, f"items[{i}]")
        roster_id = _id(row.get("roster_id"), f"items[{i}].roster_id")
        if roster_id in result:
            raise ValueError(f"list_roster 返回重复 roster_id: {roster_id}")
        employee_type = row.get("employee_type")
        if isinstance(employee_type, bool) or not isinstance(employee_type, int) or not 1 <= employee_type <= 5:
            raise ValueError(f"items[{i}].employee_type 必须为 1–5")
        result[roster_id] = {
            "roster_id": roster_id,
            "name": _str(row.get("name"), f"items[{i}].name"),
            "project_name": _str(row.get("project_name"), f"items[{i}].project_name", True),
            "company_name": _str(row.get("company_name"), f"items[{i}].company_name", True),
            "employee_type": employee_type,
            "position": _str(row.get("position"), f"items[{i}].position", True),
        }
    return result


def _candidate_map(data: object, record_ids: set[str]) -> dict[str, list[dict]]:
    data = _obj(data, "候选响应")
    if not isinstance(data.get("records"), list):
        raise ValueError("候选响应必须包含 records 数组")
    result = {}
    for i, raw in enumerate(data["records"]):
        row = _obj(raw, f"records[{i}]")
        ref = _str(row.get("client_ref"), f"records[{i}].client_ref")
        if ref not in record_ids or ref in result:
            raise ValueError(f"候选响应 client_ref 未知或重复: {ref}")
        if not isinstance(row.get("candidates"), list):
            raise ValueError(f"records[{i}].candidates 必须为数组")
        candidates, ids = [], set()
        for j, raw_candidate in enumerate(row["candidates"]):
            candidate = _obj(raw_candidate, f"records[{i}].candidates[{j}]")
            person_id = _id(candidate.get("payroll_person_id"), "payroll_person_id")
            if person_id in ids:
                raise ValueError(f"{ref} 返回重复 payroll_person_id: {person_id}")
            ids.add(person_id)
            roster_id = candidate.get("roster_id")
            if roster_id is not None:
                roster_id = _id(roster_id, "roster_id")
            employee_type = candidate.get("employee_type")
            if employee_type is not None and (
                isinstance(employee_type, bool) or not isinstance(employee_type, int) or not 1 <= employee_type <= 5
            ):
                raise ValueError("candidate.employee_type 必须为 1–5")
            roster_active = candidate.get("roster_active")
            if roster_active is not None and not isinstance(roster_active, bool):
                raise ValueError("candidate.roster_active 必须为布尔值或 null")
            roster_evidence = candidate.get("roster_evidence", [])
            if not isinstance(roster_evidence, list):
                raise ValueError("candidate.roster_evidence 必须为数组")
            normalized_roster_evidence = []
            for evidence_index, raw_evidence in enumerate(roster_evidence):
                evidence = _obj(raw_evidence, f"candidate.roster_evidence[{evidence_index}]")
                evidence_roster_id = _id(evidence.get("roster_id"), "roster_evidence.roster_id")
                active = evidence.get("active")
                evidence_type = evidence.get("employee_type")
                if not isinstance(active, bool) or isinstance(evidence_type, bool) or not isinstance(evidence_type, int) or not 1 <= evidence_type <= 5:
                    raise ValueError("candidate.roster_evidence 的 active/employee_type 无效")
                normalized_roster_evidence.append({
                    "roster_id": evidence_roster_id,
                    "active": active,
                    "project_name": _str(evidence.get("project_name"), "roster_evidence.project_name", True),
                    "company_name": _str(evidence.get("company_name"), "roster_evidence.company_name", True),
                    "employee_type": evidence_type,
                    "position": _str(evidence.get("position"), "roster_evidence.position", True),
                })
            identity_evidence = candidate.get("identity_evidence", [])
            if not isinstance(identity_evidence, list):
                raise ValueError("candidate.identity_evidence 必须为数组")
            normalized_identity_evidence = []
            for evidence_index, raw_evidence in enumerate(identity_evidence):
                evidence = _obj(raw_evidence, f"candidate.identity_evidence[{evidence_index}]")
                source = _str(evidence.get("source"), "identity_evidence.source")
                name = _str(evidence.get("name"), "identity_evidence.name")
                employee_evidence_type = evidence.get("employee_type")
                if employee_evidence_type is not None and (
                    isinstance(employee_evidence_type, bool) or not isinstance(employee_evidence_type, int)
                    or not 1 <= employee_evidence_type <= 5
                ):
                    raise ValueError("identity_evidence.employee_type 必须为 1–5")
                evidence_roster_id = evidence.get("roster_id")
                if evidence_roster_id is not None:
                    evidence_roster_id = _id(evidence_roster_id, "identity_evidence.roster_id")
                normalized_identity_evidence.append({
                    "source": source,
                    "name": name,
                    "roster_id": evidence_roster_id,
                    "project_name": _str(evidence.get("project_name"), "identity_evidence.project_name", True),
                    "company_name": _str(evidence.get("company_name"), "identity_evidence.company_name", True),
                    "employee_type": employee_evidence_type,
                    "position": _str(evidence.get("position"), "identity_evidence.position", True),
                    "source_month": _str(evidence.get("source_month"), "identity_evidence.source_month", True),
                })
            for string_field in ("match_status", "evidence_level", "project_match_status"):
                if not isinstance(candidate.get(string_field), str):
                    raise ValueError(f"candidate.{string_field} 必须为字符串")
            candidates.append({
                "payroll_person_id": person_id,
                "roster_id": roster_id,
                "name": _str(candidate.get("name"), "candidate.name"),
                "project_name": _str(candidate.get("project_name"), "candidate.project_name", True),
                "company_name": _str(candidate.get("company_name"), "candidate.company_name", True),
                "employee_type": employee_type,
                "position": _str(candidate.get("position"), "candidate.position", True),
                "roster_active": roster_active,
                "matched_fields": _string_list(candidate.get("matched_fields", []), "candidate.matched_fields"),
                "conflicting_fields": _string_list(candidate.get("conflicting_fields", []), "candidate.conflicting_fields"),
                "match_status": candidate.get("match_status"),
                "evidence_level": candidate.get("evidence_level"),
                "project_match_status": candidate.get("project_match_status"),
                "roster_evidence": normalized_roster_evidence,
                "identity_evidence": normalized_identity_evidence,
                "review_reasons": _string_list(candidate.get("review_reasons", []), "candidate.review_reasons"),
            })
        result[ref] = candidates
    if set(result) != record_ids:
        raise ValueError("候选响应必须为每条考勤记录提供唯一结果，包括空 candidates")
    return result


def _norm(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _project_alias_explains_conflict(candidate: dict, facts: dict, aliases: dict[str, str]) -> bool:
    expected = facts.get("project_name")
    raw_values = [candidate.get("project_name"), facts.get("source_project_name")]
    raw_values.extend(evidence.get("project_name") for evidence in candidate["identity_evidence"])
    raw_values.extend(evidence.get("project_name") for evidence in candidate["roster_evidence"])
    raw_values = [value.strip() for value in raw_values if isinstance(value, str) and value.strip()]
    normalized = {_canonical_project(value, aliases) for value in raw_values}
    source_project = facts.get("source_project_name")
    return bool(expected and source_project and source_project != expected and raw_values
                and normalized == {expected})


def _candidate_conflicts(candidate: dict, facts: dict, aliases: dict[str, str] | None = None) -> list[str]:
    aliases = aliases or {}
    raw_fields = set(candidate["conflicting_fields"])
    fields = raw_fields - {"position"}
    if "project_name" in fields and _project_alias_explains_conflict(candidate, facts, aliases):
        fields.remove("project_name")
    conflicts = sorted(fields)
    position_only_review = bool(candidate["review_reasons"]) and all(
        reason == "POSITION_EVIDENCE_CONFLICT" for reason in candidate["review_reasons"]
    )
    if candidate["evidence_level"] == "CONFLICTING" and (fields or (not raw_fields and not position_only_review)):
        conflicts.append("Payroll 标记 evidence_level=CONFLICTING")
    if candidate["project_match_status"] == "PROJECT_CONFLICT" and not _project_alias_explains_conflict(candidate, facts, aliases):
        conflicts.append("Payroll 标记 project_match_status=PROJECT_CONFLICT")
    for reason in candidate["review_reasons"]:
        if reason == "POSITION_EVIDENCE_CONFLICT":
            continue
        if reason == "PROJECT_EVIDENCE_CONFLICT" and _project_alias_explains_conflict(candidate, facts, aliases):
            continue
        if reason.endswith("_EVIDENCE_CONFLICT"):
            conflicts.append(reason)
    for field in ("name", *CORE_IDENTITY_FIELDS):
        source_value = facts.get(field)
        candidate_value = candidate.get(field)
        if field == "project_name":
            source_value = _canonical_project(source_value, aliases)
            candidate_value = _canonical_project(candidate_value, aliases)
        if source_value is not None and candidate_value is not None and _norm(source_value) != _norm(candidate_value):
            conflicts.append(f"{field} 与来源不一致")
        values = {
            _norm(_canonical_project(evidence.get(field), aliases) if field == "project_name" else evidence.get(field))
            for evidence in candidate["identity_evidence"]
            if evidence.get(field) is not None and evidence.get(field) != ""
        }
        if candidate.get(field) is not None and candidate.get(field) != "":
            values.add(_norm(_canonical_project(candidate[field], aliases) if field == "project_name" else candidate[field]))
        values.update({
            _norm(_canonical_project(evidence.get(field), aliases) if field == "project_name" else evidence.get(field))
            for evidence in candidate["roster_evidence"]
            if evidence.get(field) is not None and evidence.get(field) != ""
        })
        if len(values) > 1:
            conflicts.append(f"多个 Payroll 身份证据的 {field} 不一致")
    evidence_names = {
        _norm(evidence.get("name")) for evidence in candidate["identity_evidence"]
        if evidence.get("name") is not None and evidence.get("name") != ""
    }
    evidence_names.add(_norm(candidate.get("name")))
    if len(evidence_names) > 1:
        conflicts.append("多个 Payroll 身份证据的姓名不一致")
    roster_ids = {
        evidence.get("roster_id") for evidence in candidate["identity_evidence"]
        if evidence.get("roster_id") is not None
    }
    if candidate.get("roster_id") is not None:
        roster_ids.add(candidate["roster_id"])
    if len(roster_ids) > 1:
        conflicts.append("多个 Payroll 身份证据关联到不同 roster_id")
    return sorted(set(conflicts))


def _candidate_safety(candidate: dict, facts: dict, rosters: dict[int, dict], aliases: dict[str, str] | None = None) -> list[str]:
    """Return blockers for ordinary confirmation; REQUIRES_REVIEW itself is expected."""
    aliases = aliases or {}
    reasons = _candidate_conflicts(candidate, facts, aliases)
    # Payroll emits *_EVIDENCE_MISSING when a queried source field has no
    # supporting record. That is a reason to avoid automatic matching, but it
    # is not itself a contradiction and may be resolved by informed user
    # confirmation. Conflicts and multiple roster identities remain blockers.
    allowed_missing = {
        "PROJECT_EVIDENCE_MISSING",
        *(f"{field.upper()}_EVIDENCE_MISSING" for field in ("project_name", "company_name", "employee_type", "position")),
        "POSITION_EVIDENCE_CONFLICT",
    }
    reasons.extend(
        reason for reason in candidate["review_reasons"]
        if reason not in allowed_missing
        and not (reason == "PROJECT_EVIDENCE_CONFLICT" and _project_alias_explains_conflict(candidate, facts, aliases))
    )
    if candidate["match_status"] != "REQUIRES_REVIEW":
        reasons.append(f"未知或不支持的候选状态: {candidate['match_status']}")
    if candidate["evidence_level"] not in {"NAME_ONLY", "SUPPORTING", "CONFLICTING"}:
        reasons.append(f"未知候选证据等级: {candidate['evidence_level']}")
    if candidate["project_match_status"] not in {
        "PROJECT_MATCHED", "PROJECT_UNKNOWN", "PROJECT_CONFLICT", "NOT_REQUESTED",
    }:
        reasons.append(f"未知项目匹配状态: {candidate['project_match_status']}")
    roster_id = candidate["roster_id"]
    roster = rosters.get(roster_id)
    if roster is None:
        reasons.append("候选没有当前有效花名册关联")
    elif candidate["roster_active"] is not True:
        reasons.append("roster_active 未明确为 true")
    else:
        if candidate["name"] != roster["name"]:
            reasons.append("候选姓名与当前花名册不一致")
        for field in CORE_IDENTITY_FIELDS:
            candidate_value, roster_value = candidate.get(field), roster.get(field)
            if field == "project_name":
                candidate_value = _canonical_project(candidate_value, aliases)
                roster_value = _canonical_project(roster_value, aliases)
            if _norm(candidate_value) != _norm(roster_value):
                reasons.append(f"候选核心身份字段 {field} 与当前花名册不一致")
        evidence = candidate["roster_evidence"]
        if len(evidence) != 1:
            reasons.append("Payroll 返回零条或多条花名册身份依据")
        else:
            evidence_conflicts = []
            for field in CORE_IDENTITY_FIELDS:
                evidence_value, roster_value = evidence[0].get(field), roster.get(field)
                if field == "project_name":
                    evidence_value = _canonical_project(evidence_value, aliases)
                    roster_value = _canonical_project(roster_value, aliases)
                if _norm(evidence_value) != _norm(roster_value):
                    evidence_conflicts.append(field)
            if evidence[0]["roster_id"] != roster_id or evidence[0]["active"] is not True or evidence_conflicts:
                reasons.append("候选花名册证据与当前有效花名册不一致")
    if facts.get("project_name") and candidate["project_match_status"] != "PROJECT_MATCHED" and not _project_alias_explains_conflict(candidate, facts, aliases):
        reasons.append(f"项目匹配状态未确认: {candidate['project_match_status']}")
    return sorted(set(reasons))


def _candidate_advisories(candidate: dict, facts: dict) -> list[str]:
    positions = {
        _norm(value) for value in [facts.get("position"), candidate.get("position"),
                                   *(evidence.get("position") for evidence in candidate["identity_evidence"]),
                                   *(evidence.get("position") for evidence in candidate["roster_evidence"])]
        if value is not None and value != ""
    }
    return ["岗位信息存在差异（辅助信息，不阻断身份匹配）"] if len(positions) > 1 else []


def _active_roster_matches(facts: dict, rosters: dict[int, dict], aliases: dict[str, str]) -> list[dict]:
    name, project = facts.get("name"), facts.get("project_name")
    if not name or not project:
        return []
    return [
        roster for roster in rosters.values()
        if _norm(roster["name"]) == _norm(name)
        and _canonical_project(roster["project_name"], aliases) == project
    ]


def _classify(facts: dict, candidates: list[dict], rosters: dict[int, dict], aliases: dict[str, str] | None = None) -> tuple[str, int | None, list[str]]:
    aliases = aliases or {}
    if not candidates:
        return "unmatched", None, ["Payroll 未返回候选"]
    roster_matches = _active_roster_matches(facts, rosters, aliases)
    if len(roster_matches) == 1:
        roster = roster_matches[0]
        plausible = [candidate for candidate in candidates if not _candidate_conflicts(candidate, facts, aliases)]
        linked = [
            candidate for candidate in plausible
            if candidate["roster_id"] == roster["roster_id"]
            and not _candidate_safety(candidate, facts, rosters, aliases)
        ]
        if len(linked) == 1 and len(plausible) == 1:
            return "matched", linked[0]["payroll_person_id"], [
                "当前有效花名册中的姓名和规范项目唯一匹配；Payroll 人员关联由候选响应明确绑定到该 roster_id",
                *_candidate_advisories(linked[0], facts),
            ]
        if len(plausible) > 1:
            return "ambiguous", None, ["该花名册记录对应多个与已知身份事实相容的 Payroll 人员"]
        return "pending_confirmation", None, [
            "花名册姓名和规范项目唯一，但候选响应未提供唯一、有效的 Payroll 人员关联"
        ]
    required = ("name", *CORE_IDENTITY_FIELDS)
    missing = [field for field in required if facts.get(field) is None or facts.get(field) == ""]
    plausible, exact = [], []
    for candidate in candidates:
        conflicts = _candidate_conflicts(candidate, facts, aliases)
        if not conflicts:
            plausible.append(candidate)
        if not missing and not _candidate_safety(candidate, facts, rosters, aliases):
            exact.append(candidate)
    if len(exact) == 1 and len(plausible) == 1:
        return "matched", exact[0]["payroll_person_id"], ["核心身份字段与唯一有效花名册记录精确一致", *_candidate_advisories(exact[0], facts)]
    if len(exact) > 1 or len(plausible) > 1:
        return "ambiguous", None, ["存在多个与已知身份事实相容的候选"]
    reasons = []
    if missing:
        reasons.append("缺少身份字段: " + ", ".join(missing))
    if any(_candidate_conflicts(candidate, facts, aliases) for candidate in candidates):
        reasons.append("候选包含关键身份冲突")
    if any(candidate["roster_id"] not in rosters or candidate["roster_active"] is not True for candidate in candidates):
        reasons.append("候选未关联当前有效花名册记录")
    if not reasons:
        reasons.extend(_candidate_safety(candidates[0], facts, rosters, aliases) or ["候选与已知身份字段不完全一致"])
    if len(candidates) == 1:
        reasons.extend(_candidate_advisories(candidates[0], facts))
    return "pending_confirmation", None, reasons


def build(
    attendance_path: str,
    roster_path: str,
    candidates_path: str,
    existing_path: str | None = None,
    query_path: str | None = None,
    binding_path: str | None = None,
) -> dict:
    attendance, attendance_raw = _read(attendance_path)
    roster_data, roster_raw = _read(roster_path)
    candidate_data, candidate_raw = _read(candidates_path)
    _, binding_path = _binding_inputs(attendance_path, roster_path, binding_path)
    binding = project_binding.validate(attendance_path, roster_path, binding_path)
    project_map = binding["project_map"]
    binding_sha = binding["binding"]["binding_sha256"]
    people = _people(attendance, project_map)
    query_sha = _verify_query(query_path, people)
    ids = {person["record_id"] for person in people}
    rosters = _rosters(project_binding.roster_data(roster_data))
    candidate_map = _candidate_map(candidate_data, ids)
    people_by_record = {person["record_id"]: person for person in people}
    matches = []
    for person in people:
        candidates = candidate_map[person["record_id"]]
        status, person_id, reasons = _classify(person["facts"], candidates, rosters, project_map)
        roster_matches = _active_roster_matches(person["facts"], rosters, project_map)
        row = {
            "record_id": person["record_id"],
            "status": status,
            "payroll_person_id": person_id,
            "match_reasons": reasons,
            "user_confirmation": None,
        }
        if status == "matched" and len(roster_matches) == 1:
            row.update({
                "roster_id": roster_matches[0]["roster_id"],
                "match_method": "active_roster_unique",
                "reason": reasons[0],
            })
        else:
            row.update({
                "facts": person["facts"],
                "candidate_ids": [candidate["payroll_person_id"] for candidate in candidates],
                "candidates": candidates,
            })
        matches.append(row)
    result = {
        "schema_version": 1,
        "matching_rules_version": MATCHING_RULES_VERSION,
        "attendance_sha256": _sha(attendance_raw),
        "roster_sha256": _sha(roster_raw),
        "candidate_response_sha256": _sha(candidate_raw),
        "query_sha256": query_sha,
        "project_binding_sha256": binding_sha,
        "matches": matches,
    }
    if existing_path and Path(existing_path).is_file():
        previous, _ = _read(existing_path)
        if (isinstance(previous, dict) and previous.get("attendance_sha256") == result["attendance_sha256"]
                and previous.get("project_binding_sha256") == binding_sha):
            prior_rows = {row.get("record_id"): row for row in previous.get("matches", []) if isinstance(row, dict)}
            for row in result["matches"]:
                prior = prior_rows.get(row["record_id"])
                confirmed_id = prior.get("payroll_person_id") if prior and prior.get("user_confirmation") else None
                prior_candidate = next((
                    candidate for candidate in prior.get("candidates", [])
                    if isinstance(candidate, dict) and candidate.get("payroll_person_id") == confirmed_id
                ), None) if prior else None
                current_candidate = next((
                    candidate for candidate in candidate_map[row["record_id"]]
                    if candidate["payroll_person_id"] == confirmed_id
                ), None) if confirmed_id is not None else None
                if confirmed_id is not None and prior_candidate == current_candidate and current_candidate is not None:
                    facts = people_by_record[row["record_id"]]["facts"]
                    blockers = _candidate_safety(current_candidate, facts, rosters, project_map)
                    if blockers:
                        continue
                    row["status"] = "matched"
                    row["payroll_person_id"] = confirmed_id
                    row["match_reasons"] = ["保留仍存在于最新候选中的用户确认关系",
                                             *_candidate_advisories(current_candidate, facts)]
                    row["facts"] = facts
                    row["candidate_ids"] = [candidate["payroll_person_id"] for candidate in candidate_map[row["record_id"]]]
                    row["candidates"] = candidate_map[row["record_id"]]
                    row["user_confirmation"] = prior["user_confirmation"]
    return result


def confirm(
    attendance_path: str,
    roster_path: str,
    candidates_path: str,
    matches_path: str,
    request_path: str,
    query_path: str | None = None,
    binding_path: str | None = None,
) -> dict:
    _, binding_path = _binding_inputs(attendance_path, roster_path, binding_path)
    protected_paths = {
        Path(attendance_path).resolve(), Path(roster_path).resolve(), Path(candidates_path).resolve(),
        Path(request_path).resolve(), Path(binding_path).resolve(),
    }
    if query_path:
        protected_paths.add(Path(query_path).resolve())
    if Path(matches_path).resolve() in protected_paths:
        raise ValueError("person-matches 输出路径不能覆盖输入文件")
    _, attendance_raw = _read(attendance_path)
    roster_data, roster_raw = _read(roster_path)
    candidate_data, candidate_raw = _read(candidates_path)
    matches_data, _ = _read(matches_path)
    request, _ = _read(request_path)
    binding = project_binding.validate(attendance_path, roster_path, binding_path)
    project_map = binding["project_map"]
    binding_sha = binding["binding"]["binding_sha256"]
    attendance, _ = _read(attendance_path)
    people = _people(attendance, project_map)
    query_sha = _verify_query(query_path, people)
    matches_data = _obj(matches_data, "person-matches.json")
    if matches_data.get("schema_version") != 1 or matches_data.get("attendance_sha256") != _sha(attendance_raw):
        raise ValueError("考勤来源已变化或匹配文件版本无效；请重新构建候选")
    if (matches_data.get("roster_sha256") != _sha(roster_raw)
            or matches_data.get("candidate_response_sha256") != _sha(candidate_raw)
            or matches_data.get("query_sha256") != query_sha
            or matches_data.get("project_binding_sha256") != binding_sha):
        raise ValueError("Payroll 候选或项目绑定已变化；请重新构建最新映射后再确认")
    fresh = build(attendance_path, roster_path, candidates_path, query_path=query_path, binding_path=binding_path)
    current_candidates = _candidate_map(candidate_data, {person["record_id"] for person in people})
    rows = matches_data.get("matches")
    confirmations = request.get("confirmations") if isinstance(request, dict) else None
    if not isinstance(rows, list) or not isinstance(confirmations, list) or not confirmations:
        raise ValueError("person-matches 和非空 confirmations 数组为必需字段")
    by_record = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("record_id"), str) or row["record_id"] in by_record:
            raise ValueError("person-matches 包含无效或重复 record_id")
        by_record[row["record_id"]] = row
    fresh_by_record = {row["record_id"]: row for row in fresh["matches"]}
    people_by_record = {person["record_id"]: person for person in people}

    def unchanged(row: dict, current: dict, facts: dict, candidates: list[dict]) -> bool:
        if row.get("match_method") == "active_roster_unique":
            return all(row.get(field) == current.get(field) for field in (
                "status", "payroll_person_id", "roster_id", "match_method", "reason",
            ))
        return row.get("facts") == facts and row.get("candidates") == candidates

    if set(by_record) != set(fresh_by_record) or any(
        not unchanged(by_record[record_id], fresh_by_record[record_id], people_by_record[record_id]["facts"],
                      current_candidates[record_id]) for record_id in by_record
    ):
        raise ValueError("person-matches 与当前考勤或 Payroll 候选摘要不一致；请重新构建")
    roster_index = _rosters(project_binding.roster_data(roster_data))
    validated, seen = [], set()
    for i, raw in enumerate(confirmations):
        item = _obj(raw, f"confirmations[{i}]")
        record_id = _str(item.get("record_id"), f"confirmations[{i}].record_id")
        person_id = _id(item.get("payroll_person_id"), f"confirmations[{i}].payroll_person_id")
        note = _str(item.get("user_confirmation"), f"confirmations[{i}].user_confirmation")
        if not note:
            raise ValueError(f"confirmations[{i}] 缺少用户确认依据")
        if record_id in seen:
            raise ValueError(f"批次 record_id 重复: {record_id}")
        seen.add(record_id)
        row = by_record.get(record_id)
        if row is None:
            raise ValueError(f"找不到考勤 record_id: {record_id}")
        row_candidates = row.get("candidates") or current_candidates[record_id]
        if not any(
            isinstance(candidate, dict) and candidate.get("payroll_person_id") == person_id
            for candidate in row_candidates
        ):
            raise ValueError(f"人员 {person_id} 不属于 {record_id} 的候选列表")
        selected = next(candidate for candidate in row_candidates if candidate["payroll_person_id"] == person_id)
        facts = people_by_record[record_id]["facts"]
        blockers = _candidate_safety(selected, facts, roster_index, project_map)
        if blockers:
            raise ValueError(f"人员 {person_id} 不能普通确认: " + "; ".join(blockers))
        validated.append((row, person_id, note, selected, facts))
    for row, person_id, note, selected, facts in validated:
        row["status"] = "matched"
        row["payroll_person_id"] = person_id
        row["facts"] = facts
        row["candidates"] = row.get("candidates") or current_candidates[row["record_id"]]
        row["candidate_ids"] = [candidate["payroll_person_id"] for candidate in row["candidates"]]
        row["match_reasons"] = ["用户明确确认候选关系", *_candidate_advisories(selected, facts)]
        row["user_confirmation"] = {"source": "user", "note": note}
    _write(matches_path, matches_data)
    return matches_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    request_parser = sub.add_parser("candidate-request", help="生成当前考勤对应的确定性 Payroll 候选请求")
    request_parser.add_argument("--attendance", required=True)
    request_parser.add_argument("--roster", required=True)
    request_parser.add_argument("--binding", required=True)
    request_parser.add_argument("--output", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--attendance", required=True)
    build_parser.add_argument("--roster", required=True)
    build_parser.add_argument("--candidates", required=True)
    build_parser.add_argument("--query", required=True, help="实际发送给 Payroll 候选接口的请求 JSON")
    build_parser.add_argument("--binding", required=True)
    build_parser.add_argument("--output", required=True)
    confirm_parser = sub.add_parser("confirm")
    confirm_parser.add_argument("--attendance", required=True)
    confirm_parser.add_argument("--roster", required=True)
    confirm_parser.add_argument("--candidates", required=True)
    confirm_parser.add_argument("--matches", required=True)
    confirm_parser.add_argument("--request", required=True)
    confirm_parser.add_argument("--query", required=True, help="实际发送给 Payroll 候选接口的请求 JSON")
    confirm_parser.add_argument("--binding", required=True)
    args = parser.parse_args()
    status_counts = None
    if args.command == "candidate-request":
        if Path(args.output).resolve() in {Path(args.attendance).resolve(), Path(args.roster).resolve(),
                                           Path(args.binding).resolve()}:
            raise ValueError("候选请求输出路径不能覆盖输入文件")
        result = candidate_request(args.attendance, args.roster, args.binding)
        _write(args.output, result)
        output_path = args.output
        result_count = len(result["records"])
    elif args.command == "build":
        if Path(args.output).resolve() in {
            Path(args.attendance).resolve(), Path(args.roster).resolve(), Path(args.candidates).resolve(),
            Path(args.query).resolve(), Path(args.binding).resolve(),
        }:
            raise ValueError("person-matches 输出路径不能覆盖输入文件")
        result = build(args.attendance, args.roster, args.candidates, query_path=args.query, binding_path=args.binding)
        output_path = args.output
        _write(output_path, result)
        result_count = len(result["matches"])
        status_counts = {
            status: sum(row["status"] == status for row in result["matches"])
            for status in ("matched", "ambiguous", "unmatched", "pending_confirmation")
        }
    else:
        result = confirm(args.attendance, args.roster, args.candidates, args.matches, args.request,
                         query_path=args.query, binding_path=args.binding)
        output_path = args.matches
        result_count = len(result["matches"])
    response = {"ok": True, "count": result_count, "path": output_path}
    if status_counts is not None:
        response["status_counts"] = status_counts
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
