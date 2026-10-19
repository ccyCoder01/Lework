import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from person_matches import _candidate_map, _classify, build, candidate_request, confirm  # noqa: E402


def attendance(*, complete=True, count=1):
    people = []
    for i in range(count):
        person = {
            "record_id": f"doc-1-p1-r{i + 1}",
            "name": "张伟",
            "position": "施工员",
            "project": "项目甲",
            "daily": [{"day": 1, "raw_mark": "?", "status": "unknown"}],
        }
        people.append(person)
    return {"schema_version": 1, "month": "2026-06", "people": people}


def candidate(person_id=41, *, project="项目甲", company="甲公司", employee_type=1,
              position="施工员", roster_id=7, conflicts=None, name="张伟", roster_active=True,
              project_status="PROJECT_MATCHED", review_reasons=None, extra_identity_evidence=None):
    conflicts = conflicts or []
    return {
        "payroll_person_id": person_id,
        "roster_id": roster_id,
        "roster_active": roster_active,
        "name": name,
        "project_name": project,
        "company_name": company,
        "employee_type": employee_type,
        "position": position,
        "matched_fields": ["name", "project_name", "company_name", "employee_type", "position"],
        "conflicting_fields": conflicts,
        "match_status": "REQUIRES_REVIEW",
        "evidence_level": "CONFLICTING" if conflicts else "SUPPORTING",
        "project_match_status": project_status,
        "roster_evidence": [{
            "roster_id": roster_id, "active": True, "project_name": project,
            "company_name": company, "employee_type": employee_type, "position": position,
        }],
        "identity_evidence": extra_identity_evidence or [],
        "review_reasons": review_reasons if review_reasons is not None else [f"{field.upper()}_EVIDENCE_CONFLICT" for field in conflicts],
    }


def fixtures(tmp_path, *, source=None, roster_rows=None, candidate_rows=None):
    source = source or attendance()
    roster_rows = roster_rows if roster_rows is not None else [{
        "roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
        "employee_type": 1, "position": "施工员", "gender": 0,
    }]
    ids = [person["record_id"] for person in source["people"]]
    candidate_rows = candidate_rows if candidate_rows is not None else [
        {"client_ref": record_id, "candidates": [candidate(person_id=41 + i, roster_id=7 + i)]}
        for i, record_id in enumerate(ids)
    ]
    attendance_path = tmp_path / "attendance.json"
    roster_path = tmp_path / "list-roster.json"
    candidate_path = tmp_path / "candidates.json"
    attendance_path.write_text(json.dumps(source), encoding="utf-8")
    roster_path.write_text(json.dumps({"count": len(roster_rows), "items": roster_rows}), encoding="utf-8")
    candidate_path.write_text(json.dumps({"records": candidate_rows}), encoding="utf-8")
    return attendance_path, roster_path, candidate_path


def build_to_file(tmp_path, **kwargs):
    attendance_path, roster_path, candidate_path = fixtures(tmp_path, **kwargs)
    result = build(str(attendance_path), str(roster_path), str(candidate_path))
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(result), encoding="utf-8")
    return attendance_path, matches_path, result


def test_complete_exact_identity_matches_unique_active_roster(tmp_path):
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "施工员"}}
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "项目甲", "company_name": "甲公司", "employee_type": 1, "position": "施工员"},
        [candidate()], roster,
    )
    assert status == "matched" and payroll_person_id == 41


def test_exact_candidate_plus_another_reasonable_candidate_is_ambiguous():
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "施工员"}}
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "项目甲", "company_name": "甲公司", "employee_type": 1, "position": "施工员"},
        [candidate(), candidate(42, roster_id=8)], roster,
    )
    assert status == "ambiguous" and payroll_person_id is None


def test_exact_candidate_plus_explicitly_conflicting_candidate_can_match_unique_identity():
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "施工员"}}
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "项目甲", "company_name": "甲公司", "employee_type": 1, "position": "施工员"},
        [candidate(), candidate(42, project="项目乙", roster_id=8, conflicts=["project_name"])], roster,
    )
    assert status == "matched" and payroll_person_id == 41


def test_unique_active_roster_matches_without_source_company_or_employee_type(tmp_path):
    _, _, result = build_to_file(tmp_path)
    row = result["matches"][0]
    assert row["status"] == "matched"
    assert row["payroll_person_id"] == 41
    assert row["roster_id"] == 7
    assert row["match_method"] == "active_roster_unique"
    assert "candidates" not in row and "candidate_ids" not in row


def test_build_cli_reports_status_counts_without_changing_existing_fields(tmp_path):
    attendance_path, roster_path, candidate_path = fixtures(tmp_path)
    output_path = tmp_path / "person-matches.json"
    query_path = tmp_path / "candidate-query.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "person_matches.py"
    query_result = subprocess.run([
        sys.executable, str(script), "candidate-request", "--attendance", str(attendance_path),
        "--output", str(query_path),
    ], check=True, capture_output=True, text=True)
    assert json.loads(query_result.stdout) == {"ok": True, "count": 1, "path": str(query_path)}
    result = subprocess.run([
        sys.executable, str(script), "build", "--attendance", str(attendance_path),
        "--roster", str(roster_path), "--candidates", str(candidate_path),
        "--query", str(query_path), "--output", str(output_path),
    ], check=True, capture_output=True, text=True)
    response = json.loads(result.stdout)
    assert response["ok"] is True and response["count"] == 1 and response["path"] == str(output_path)
    assert response["status_counts"] == {
        "matched": 1, "ambiguous": 0, "unmatched": 0, "pending_confirmation": 0,
    }


def test_roster_id_is_not_used_as_payroll_person_id(tmp_path):
    roster_rows = [{"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                    "employee_type": 1, "position": "施工员", "gender": 0}]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [candidate(person_id=43, roster_id=7)]}]
    _, _, result = build_to_file(tmp_path, roster_rows=roster_rows, candidate_rows=candidate_rows)
    row = result["matches"][0]
    assert row["status"] == "matched"
    assert row["payroll_person_id"] == 43
    assert row["roster_id"] == 7


def test_missing_candidate_roster_link_never_guesses_payroll_person_id(tmp_path):
    roster_rows = [{"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                    "employee_type": 1, "position": "施工员", "gender": 0}]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [candidate(person_id=43, roster_id=8)]}]
    _, _, result = build_to_file(tmp_path, roster_rows=roster_rows, candidate_rows=candidate_rows)
    row = result["matches"][0]
    assert row["status"] == "pending_confirmation"
    assert row["payroll_person_id"] is None


def test_missing_payroll_person_id_in_candidate_response_is_rejected(tmp_path):
    bad = candidate()
    del bad["payroll_person_id"]
    with pytest.raises(ValueError, match="payroll_person_id"):
        build_to_file(tmp_path, candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [bad]}])


def test_same_name_same_project_multiple_rosters_requires_deep_resolution(tmp_path):
    roster_rows = [
        {"roster_id": roster_id, "name": "张伟", "project_name": "项目甲", "company_name": company,
         "employee_type": 1, "position": position, "gender": 0}
        for roster_id, company, position in [(7, "甲公司", "施工员"), (8, "乙公司", "电工")]
    ]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [
        candidate(person_id=41, roster_id=7), candidate(person_id=42, roster_id=8, company="乙公司", position="电工"),
    ]}]
    _, _, result = build_to_file(tmp_path, roster_rows=roster_rows, candidate_rows=candidate_rows)
    assert result["matches"][0]["status"] == "ambiguous"


def test_deep_candidate_can_disambiguate_when_full_identity_facts_exist(tmp_path):
    source = attendance()
    source["people"][0].update({"company_name": "甲公司", "employee_type": 1})
    roster_rows = [
        {"roster_id": roster_id, "name": "张伟", "project_name": "项目甲", "company_name": company,
         "employee_type": 1, "position": position, "gender": 0}
        for roster_id, company, position in [(7, "甲公司", "施工员"), (8, "乙公司", "电工")]
    ]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [
        candidate(person_id=41, roster_id=7),
        candidate(person_id=42, roster_id=8, company="乙公司", position="电工", conflicts=["company_name"]),
    ]}]
    _, _, result = build_to_file(tmp_path, source=source, roster_rows=roster_rows, candidate_rows=candidate_rows)
    row = result["matches"][0]
    assert row["status"] == "matched" and row["payroll_person_id"] == 41
    assert row.get("match_method") is None
    assert "candidates" in row


def test_same_name_different_project_does_not_fast_match(tmp_path):
    roster_rows = [{"roster_id": 7, "name": "张伟", "project_name": "项目乙", "company_name": "甲公司",
                    "employee_type": 1, "position": "施工员", "gender": 0}]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [
        candidate(project="项目乙", roster_id=7, conflicts=["project_name"], project_status="PROJECT_CONFLICT",
                  review_reasons=["PROJECT_EVIDENCE_CONFLICT"]),
    ]}]
    _, _, result = build_to_file(tmp_path, roster_rows=roster_rows, candidate_rows=candidate_rows)
    assert result["matches"][0]["status"] == "pending_confirmation"
    assert result["matches"][0]["payroll_person_id"] is None


def test_yangling_project_alias_is_exact_and_matches_active_roster(tmp_path):
    source = attendance()
    source["people"][0]["project"] = "杨凌职业技术学院新校区项目"
    roster_rows = [{"roster_id": 93, "name": "张伟", "project_name": "杨职院", "company_name": "甲公司",
                    "employee_type": 1, "position": "施工员", "gender": 0}]
    candidate_rows = [{"client_ref": "doc-1-p1-r1", "candidates": [
        candidate(person_id=43, project="杨职院", roster_id=93),
    ]}]
    attendance_path, _, result = build_to_file(tmp_path, source=source, roster_rows=roster_rows, candidate_rows=candidate_rows)
    row = result["matches"][0]
    assert row["status"] == "matched" and row["payroll_person_id"] == 43
    assert row["roster_id"] == 93
    assert candidate_request(str(attendance_path))["records"][0]["project_name"] == "杨职院"


@pytest.mark.parametrize("field,value", [
    ("project_name", "项目乙"),
    ("company_name", "乙公司"),
    ("employee_type", 2),
])
def test_same_name_different_identity_fact_never_auto_matches(tmp_path, field, value):
    source = attendance(complete=False)
    if field == "company_name":
        source["people"][0][field] = "甲公司"
    elif field == "employee_type":
        source["people"][0][field] = 1
    roster = candidate()
    roster[field] = value
    roster_item = {
        "roster_id": 7, "name": "张伟", "project_name": roster["project_name"],
        "company_name": roster["company_name"], "employee_type": roster["employee_type"],
        "position": roster["position"], "gender": 0,
    }
    _, _, result = build_to_file(
        tmp_path, source=source, roster_rows=[roster_item],
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [roster]}],
    )
    assert result["matches"][0]["status"] == "pending_confirmation"
    assert result["matches"][0]["payroll_person_id"] is None


def test_position_mismatch_is_soft_when_active_roster_link_is_unique(tmp_path):
    source = attendance(complete=False)
    candidate_row = candidate(position="电工")
    roster_row = {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "电工"}
    _, _, result = build_to_file(
        tmp_path, source=source, roster_rows=[roster_row],
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [candidate_row]}],
    )
    assert result["matches"][0]["status"] == "matched"
    assert any("岗位信息存在差异" in reason for reason in result["matches"][0]["match_reasons"])


def test_position_is_soft_when_core_identity_is_complete():
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "电工"}}
    position_conflict = candidate(position="电工", conflicts=["position"], review_reasons=["POSITION_EVIDENCE_CONFLICT"])
    status, payroll_person_id, reasons = _classify(
        {"name": "张伟", "project_name": "项目甲", "company_name": "甲公司", "employee_type": 1,
         "position": "施工员"},
        [position_conflict], roster,
    )
    assert status == "matched" and payroll_person_id == 41
    assert any("岗位信息存在差异" in reason for reason in reasons)


def test_missing_position_does_not_block_complete_core_identity():
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "施工员"}}
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "项目甲", "company_name": "甲公司", "employee_type": 1,
         "position": None},
        [candidate()], roster,
    )
    assert status == "matched" and payroll_person_id == 41


def test_explicit_hanyue_alias_normalizes_candidate_request_and_explains_only_alias_conflict(tmp_path):
    source = attendance()
    source["people"][0].update({"project": "瀚阅府西苑项目", "company_name": "甲公司", "employee_type": 1})
    attendance_path, roster_path, candidate_path = fixtures(tmp_path, source=source)
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "canonical": "瀚阅府", "aliases": ["瀚阅府西苑项目"],
    }]}), encoding="utf-8")
    request = candidate_request(str(attendance_path), alias_path)
    assert request == {"records": [{"client_ref": "doc-1-p1-r1", "name": "张伟",
                                     "project_name": "瀚阅府", "company_name": "甲公司", "employee_type": 1}]}
    assert "position" not in request["records"][0]
    source["people"][0]["project"] = "瀚阅府"
    attendance_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    assert candidate_request(str(attendance_path), alias_path)["records"][0]["project_name"] == "瀚阅府"

    alias_candidate = candidate(project="瀚阅府", conflicts=["project_name"], project_status="PROJECT_CONFLICT",
                                review_reasons=["PROJECT_EVIDENCE_CONFLICT"])
    response = {"records": [{"client_ref": "doc-1-p1-r1", "candidates": [alias_candidate]}]}
    candidate_path.write_text(json.dumps(response), encoding="utf-8")
    roster = {7: {"roster_id": 7, "name": "张伟", "project_name": "瀚阅府", "company_name": "甲公司",
                  "employee_type": 1, "position": "施工员"}}
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "瀚阅府", "source_project_name": "瀚阅府西苑项目",
         "company_name": "甲公司", "employee_type": 1, "position": "施工员"},
        [alias_candidate], roster, {"瀚阅府": "瀚阅府", "瀚阅府西苑项目": "瀚阅府"},
    )
    assert status == "matched" and payroll_person_id == 41


def test_candidate_query_must_match_current_alias_normalization(tmp_path):
    source = attendance()
    source["people"][0].update({"project": "瀚阅府西苑项目", "company_name": "甲公司", "employee_type": 1})
    attendance_path, roster_path, candidate_path = fixtures(tmp_path, source=source)
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "canonical": "瀚阅府", "aliases": ["瀚阅府西苑项目"],
    }]}), encoding="utf-8")
    query_path = tmp_path / "candidate-query.json"
    query_path.write_text(json.dumps({"records": [{"client_ref": "doc-1-p1-r1", "name": "张伟",
                                                   "project_name": "错误项目", "company_name": "甲公司",
                                                   "employee_type": 1}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="查询请求与当前考勤"):
        build(str(attendance_path), str(roster_path), str(candidate_path), query_path=str(query_path),
              aliases_path=alias_path)


def test_non_alias_project_difference_remains_a_conflict():
    other = candidate(project="瀚阅府东苑", conflicts=["project_name"], project_status="PROJECT_CONFLICT",
                      review_reasons=["PROJECT_EVIDENCE_CONFLICT"])
    status, payroll_person_id, _ = _classify(
        {"name": "张伟", "project_name": "瀚阅府", "company_name": "甲公司", "employee_type": 1},
        [other], {7: {"roster_id": 7, "name": "张伟", "project_name": "瀚阅府东苑", "company_name": "甲公司",
                      "employee_type": 1, "position": "施工员"}},
        {"瀚阅府": "瀚阅府", "瀚阅府西苑项目": "瀚阅府"},
    )
    assert status == "pending_confirmation" and payroll_person_id is None


def test_position_conflict_does_not_block_explicit_confirmation(tmp_path):
    source = attendance(complete=False)
    roster_row = {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                  "employee_type": 1, "position": "电工", "gender": 0}
    reviewed = candidate(position="电工", conflicts=["position"], review_reasons=["POSITION_EVIDENCE_CONFLICT"])
    attendance_path, roster_path, candidate_path = fixtures(
        tmp_path, source=source, roster_rows=[roster_row],
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [reviewed]}],
    )
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(build(str(attendance_path), str(roster_path), str(candidate_path))), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "已查看并确认该身份",
    }]}), encoding="utf-8")
    result = confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path), str(request_path))
    assert result["matches"][0]["status"] == "matched"
    assert any("岗位信息存在差异" in reason for reason in result["matches"][0]["match_reasons"])


def test_batch_confirmation_keeps_position_advisories_with_their_own_record(tmp_path):
    roster_rows = [
        {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
         "employee_type": 1, "position": "电工", "gender": 0},
        {"roster_id": 8, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
         "employee_type": 1, "position": "施工员", "gender": 0},
    ]
    candidate_rows = [
        {"client_ref": "doc-1-p1-r1", "candidates": [candidate(41, position="电工", roster_id=7,
                                                                     conflicts=["position"],
                                                                     review_reasons=["POSITION_EVIDENCE_CONFLICT"])]},
        {"client_ref": "doc-1-p1-r2", "candidates": [candidate(42, roster_id=8)]},
    ]
    attendance_path, roster_path, candidates_path = fixtures(
        tmp_path, source=attendance(complete=False, count=2), roster_rows=roster_rows,
        candidate_rows=candidate_rows,
    )
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(build(str(attendance_path), str(roster_path), str(candidates_path))), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [
        {"record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "确认第一人"},
        {"record_id": "doc-1-p1-r2", "payroll_person_id": 42, "user_confirmation": "确认第二人"},
    ]}), encoding="utf-8")
    result = confirm(str(attendance_path), str(roster_path), str(candidates_path),
                     str(matches_path), str(request_path))
    reasons = {row["record_id"]: row["match_reasons"] for row in result["matches"]}
    assert any("岗位信息存在差异" in reason for reason in reasons["doc-1-p1-r1"])
    assert not any("岗位信息存在差异" in reason for reason in reasons["doc-1-p1-r2"])


def test_explicit_project_alias_is_consistent_through_confirmation(tmp_path):
    source = attendance(complete=False)
    source["people"][0]["project"] = "瀚阅府西苑项目"
    attendance_path, _, candidate_path = fixtures(
        tmp_path, source=source,
        roster_rows=[{"roster_id": 7, "name": "张伟", "project_name": "瀚阅府", "company_name": "甲公司",
                      "employee_type": 1, "position": "施工员", "gender": 0}],
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [candidate(
            project="瀚阅府", conflicts=["project_name"], project_status="PROJECT_CONFLICT",
            review_reasons=["PROJECT_EVIDENCE_CONFLICT"],
        )]}],
    )
    roster_path = tmp_path / "list-roster.json"
    alias_path = tmp_path / "aliases.json"
    alias_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "canonical": "瀚阅府", "aliases": ["瀚阅府西苑项目"],
    }]}), encoding="utf-8")
    query = candidate_request(str(attendance_path), alias_path)
    query_path = tmp_path / "candidate-query.json"
    query_path.write_text(json.dumps(query, ensure_ascii=False), encoding="utf-8")
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(build(
        str(attendance_path), str(roster_path), str(candidate_path),
        query_path=str(query_path), aliases_path=alias_path,
    )), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "已核实项目别名及人员身份",
    }]}), encoding="utf-8")
    result = confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path),
                     str(request_path), query_path=str(query_path), aliases_path=alias_path)
    assert result["matches"][0]["status"] == "matched"


def test_multiple_candidates_are_ambiguous_and_no_candidate_is_unmatched(tmp_path):
    source = attendance(complete=False)
    _, _, result = build_to_file(
        tmp_path,
        source=source,
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [candidate(41), candidate(42, roster_id=8)]}],
    )
    assert result["matches"][0]["status"] == "ambiguous"
    _, _, empty = build_to_file(
        tmp_path,
        source=source,
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": []}],
    )
    assert empty["matches"][0]["status"] == "unmatched"


def test_duplicate_candidate_id_rejected(tmp_path):
    source = attendance()
    with pytest.raises(ValueError, match="重复 payroll_person_id"):
        build_to_file(
            tmp_path,
            source=source,
            candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [candidate(41), candidate(41, roster_id=8)]}],
        )


def test_user_confirmation_links_only_returned_candidate_and_does_not_change_attendance(tmp_path):
    attendance_path, matches_path, _ = build_to_file(tmp_path, source=attendance(complete=False))
    original_attendance = attendance_path.read_bytes()
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户明确确认张伟对应此候选",
    }]}), encoding="utf-8")
    result = confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    row = result["matches"][0]
    assert row["status"] == "matched" and row["payroll_person_id"] == 41
    assert row["user_confirmation"]["source"] == "user"
    assert attendance_path.read_bytes() == original_attendance
    assert row["facts"]["employee_type"] is None
    assert json.loads(attendance_path.read_text())["people"][0]["daily"][0]["status"] == "unknown"


def test_ordinary_confirmation_allows_missing_source_evidence_after_candidate_review(tmp_path):
    reviewed = candidate(review_reasons=[
        "COMPANY_NAME_EVIDENCE_MISSING", "EMPLOYEE_TYPE_EVIDENCE_MISSING",
    ])
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False),
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [reviewed]}],
    )
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41,
        "user_confirmation": "用户已查看公司和用工类别并明确确认",
    }]}), encoding="utf-8")
    result = confirm(
        str(attendance_path), str(tmp_path / "list-roster.json"),
        str(tmp_path / "candidates.json"), str(matches_path), str(request_path),
    )
    assert result["matches"][0]["status"] == "matched"


@pytest.mark.parametrize("bad_candidate,roster_rows", [
    (candidate(conflicts=["company_name"]), None),
    (candidate(conflicts=["employee_type"]), None),
    (candidate(name="张伟斌"), None),
    (candidate(project_status="PROJECT_CONFLICT"), None),
    (candidate(project_status="UNRECOGNIZED_STATUS"), None),
    (candidate(), []),
    (candidate(), [{"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "乙公司",
                    "employee_type": 1, "position": "施工员", "gender": 0}]),
    (candidate(roster_active=False), None),
    (candidate(review_reasons=["MULTIPLE_ROSTER_IDENTITIES"]), None),
])
def test_ordinary_confirmation_rejects_conflicting_or_unlinked_candidate(tmp_path, bad_candidate, roster_rows):
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False), roster_rows=roster_rows,
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [bad_candidate]}],
    )
    before = matches_path.read_bytes()
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户确认该候选",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="不能普通确认"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before


def test_user_can_choose_safe_candidate_but_not_conflicting_candidate(tmp_path):
    safe = candidate(41)
    conflicting = candidate(42, company="乙公司", roster_id=8, conflicts=["company_name"])
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False), candidate_rows=[{
            "client_ref": "doc-1-p1-r1", "candidates": [safe, conflicting],
        }],
    )
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 42, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    before = matches_path.read_bytes()
    with pytest.raises(ValueError, match="不能普通确认"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before


def test_ordinary_confirmation_rejects_conflicting_payroll_identity_evidence(tmp_path):
    conflicted = candidate(extra_identity_evidence=[{
        "source": "historical_salary", "name": "张伟", "company_name": "乙公司",
    }])
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False),
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [conflicted]}],
    )
    before = matches_path.read_bytes()
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="company_name 不一致"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before


def test_ordinary_confirmation_rejects_multiple_roster_ids_in_identity_evidence(tmp_path):
    conflicted = candidate(extra_identity_evidence=[{
        "source": "historical_salary", "name": "张伟", "roster_id": 8,
    }])
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False),
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [conflicted]}],
    )
    before = matches_path.read_bytes()
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="不同 roster_id"):
        confirm(
            str(attendance_path), str(tmp_path / "list-roster.json"),
            str(tmp_path / "candidates.json"), str(matches_path), str(request_path),
        )
    assert matches_path.read_bytes() == before


def test_non_candidate_or_missing_record_confirmation_rejected_without_write(tmp_path):
    attendance_path, matches_path, _ = build_to_file(tmp_path, source=attendance(complete=False))
    before = matches_path.read_bytes()
    request_path = tmp_path / "bad.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 999, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="不属于"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "missing", "payroll_person_id": 41, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    with pytest.raises(ValueError, match="找不到考勤 record_id"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before


def test_confirmation_rejects_tampered_mapping_or_changed_candidate_response(tmp_path):
    attendance_path, matches_path, _ = build_to_file(tmp_path, source=attendance(complete=False))
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 999, "user_confirmation": "用户确认",
    }]}), encoding="utf-8")
    original = json.loads(matches_path.read_text(encoding="utf-8"))
    original["matches"][0]["payroll_person_id"] = 999
    matches_path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="候选摘要不一致"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    refreshed = build(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"))
    matches_path.write_text(json.dumps(refreshed), encoding="utf-8")
    changed = json.loads((tmp_path / "candidates.json").read_text(encoding="utf-8"))
    changed["records"][0]["candidates"][0]["review_reasons"] = ["更新"]
    (tmp_path / "candidates.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="候选输入已变化"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))


def test_confirmation_batch_validates_all_items_before_atomic_write(tmp_path):
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False, count=2),
        candidate_rows=[
            {"client_ref": "doc-1-p1-r1", "candidates": [candidate(41)]},
            {"client_ref": "doc-1-p1-r2", "candidates": [candidate(42, roster_id=8)]},
        ],
    )
    before = matches_path.read_bytes()
    request_path = tmp_path / "batch.json"
    request_path.write_text(json.dumps({"confirmations": [
        {"record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "确认一"},
        {"record_id": "doc-1-p1-r2", "payroll_person_id": 999, "user_confirmation": "确认二"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="不属于"):
        confirm(str(attendance_path), str(tmp_path / "list-roster.json"), str(tmp_path / "candidates.json"), str(matches_path), str(request_path))
    assert matches_path.read_bytes() == before


def test_batch_with_unsafe_identity_candidate_is_atomic(tmp_path):
    unsafe = candidate(42, roster_id=8, conflicts=["employee_type"])
    attendance_path, matches_path, _ = build_to_file(
        tmp_path, source=attendance(complete=False, count=2),
        candidate_rows=[
            {"client_ref": "doc-1-p1-r1", "candidates": [candidate(41)]},
            {"client_ref": "doc-1-p1-r2", "candidates": [unsafe]},
        ],
    )
    before = matches_path.read_bytes()
    request_path = tmp_path / "batch.json"
    request_path.write_text(json.dumps({"confirmations": [
        {"record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "确认一"},
        {"record_id": "doc-1-p1-r2", "payroll_person_id": 42, "user_confirmation": "确认二"},
    ]}), encoding="utf-8")
    with pytest.raises(ValueError, match="不能普通确认"):
        confirm(
            str(attendance_path), str(tmp_path / "list-roster.json"),
            str(tmp_path / "candidates.json"), str(matches_path), str(request_path),
        )
    assert matches_path.read_bytes() == before


def test_rebuild_preserves_user_confirmation_only_if_candidate_still_exists(tmp_path):
    reviewed = candidate(position="电工", conflicts=["position"], review_reasons=["POSITION_EVIDENCE_CONFLICT"])
    attendance_path, roster_path, candidate_path = fixtures(
        tmp_path, source=attendance(complete=False),
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [reviewed]}],
    )
    matches_path = tmp_path / "person-matches.json"
    first = build(str(attendance_path), str(roster_path), str(candidate_path))
    matches_path.write_text(json.dumps(first), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户确认关系",
    }]}), encoding="utf-8")
    confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path), str(request_path))
    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path))
    assert refreshed["matches"][0]["status"] == "matched"
    assert refreshed["matches"][0]["user_confirmation"]["note"] == "用户确认关系"
    assert any("岗位信息存在差异" in reason for reason in refreshed["matches"][0]["match_reasons"])
    changed_candidates = {"records": [{"client_ref": "doc-1-p1-r1", "candidates": [candidate(88)]}]}
    candidate_path.write_text(json.dumps(changed_candidates), encoding="utf-8")
    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path))
    assert refreshed["matches"][0]["payroll_person_id"] == 88
    assert refreshed["matches"][0]["match_method"] == "active_roster_unique"
    assert refreshed["matches"][0]["user_confirmation"] is None


def test_rebuild_drops_confirmation_when_current_roster_identity_changes(tmp_path):
    attendance_path, roster_path, candidate_path = fixtures(tmp_path, source=attendance(complete=False))
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(build(str(attendance_path), str(roster_path), str(candidate_path))), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "用户确认关系",
    }]}), encoding="utf-8")
    confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path), str(request_path))
    changed_roster = {"count": 1, "items": [{
        "roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "乙公司",
        "employee_type": 1, "position": "施工员", "gender": 0,
    }]}
    roster_path.write_text(json.dumps(changed_roster), encoding="utf-8")
    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path))
    assert refreshed["matches"][0]["status"] == "pending_confirmation"
    assert refreshed["matches"][0]["payroll_person_id"] is None
    assert refreshed["matches"][0]["user_confirmation"] is None


def test_alias_change_does_not_reuse_previous_confirmation(tmp_path):
    source = attendance()
    source["people"][0]["project"] = "项目别名"
    attendance_path, roster_path, candidate_path = fixtures(
        tmp_path, source=source,
        roster_rows=[{"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
                      "employee_type": 1, "position": "施工员", "gender": 0}],
        candidate_rows=[{"client_ref": "doc-1-p1-r1", "candidates": [candidate()]}],
    )
    aliases_path = tmp_path / "aliases.json"
    aliases_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "canonical": "项目甲", "aliases": ["项目别名"],
    }]}), encoding="utf-8")
    matches_path = tmp_path / "person-matches.json"
    initial = build(str(attendance_path), str(roster_path), str(candidate_path), aliases_path=aliases_path)
    assert initial["matches"][0]["status"] == "matched"
    assert initial["matching_rules_version"] == "W03.3"
    matches_path.write_text(json.dumps(initial), encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [{
        "record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "确认该候选",
    }]}), encoding="utf-8")
    confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path), str(request_path),
            aliases_path=aliases_path)

    aliases_path.write_text(json.dumps({"schema_version": 1, "projects": [{
        "canonical": "项目乙", "aliases": ["项目别名"],
    }]}), encoding="utf-8")
    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path),
                      existing_path=str(matches_path), aliases_path=aliases_path)
    row = refreshed["matches"][0]
    assert row["status"] == "pending_confirmation"
    assert row["user_confirmation"] is None


def test_w03_2_mapping_shape_is_read_and_confirmation_revalidated(tmp_path):
    attendance_path, roster_path, candidate_path = fixtures(tmp_path)
    legacy = build(str(attendance_path), str(roster_path), str(candidate_path))
    person_facts = {
        "name": "张伟", "source_project_name": "项目甲", "project_name": "项目甲",
        "company_name": None, "employee_type": None, "position": "施工员",
    }
    row = legacy["matches"][0]
    row.update({
        "facts": person_facts,
        "candidate_ids": [41],
        "candidates": _candidate_map(json.loads(candidate_path.read_text(encoding="utf-8")),
                                      {"doc-1-p1-r1"})["doc-1-p1-r1"],
        "user_confirmation": {"source": "user", "note": "W03.2 用户确认"},
    })
    for field in ("roster_id", "match_method", "reason"):
        row.pop(field, None)
    legacy.pop("matching_rules_version", None)
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(legacy), encoding="utf-8")

    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path), existing_path=str(matches_path))
    current = refreshed["matches"][0]
    assert current["status"] == "matched" and current["payroll_person_id"] == 41
    assert current["user_confirmation"]["note"] == "W03.2 用户确认"


def test_rebuild_revalidates_each_confirmation_against_its_own_attendance_record(tmp_path):
    source = attendance(count=2)
    source["people"][1].update({
        "name": "李伟", "project": "项目乙", "company_name": "乙公司", "employee_type": 2,
    })
    roster_rows = [
        {"roster_id": 7, "name": "张伟", "project_name": "项目甲", "company_name": "甲公司",
         "employee_type": 1, "position": "施工员", "gender": 0},
        {"roster_id": 8, "name": "李伟", "project_name": "项目乙", "company_name": "乙公司",
         "employee_type": 2, "position": "施工员", "gender": 0},
    ]
    candidate_rows = [
        {"client_ref": "doc-1-p1-r1", "candidates": [candidate(41)]},
        {"client_ref": "doc-1-p1-r2", "candidates": [candidate(42, name="李伟", project="项目乙",
                                                                  company="乙公司", employee_type=2, roster_id=8)]},
    ]
    attendance_path, roster_path, candidate_path = fixtures(
        tmp_path, source=source, roster_rows=roster_rows, candidate_rows=candidate_rows,
    )
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps(build(str(attendance_path), str(roster_path), str(candidate_path))),
                            encoding="utf-8")
    request_path = tmp_path / "confirm.json"
    request_path.write_text(json.dumps({"confirmations": [
        {"record_id": "doc-1-p1-r1", "payroll_person_id": 41, "user_confirmation": "确认张伟"},
        {"record_id": "doc-1-p1-r2", "payroll_person_id": 42, "user_confirmation": "确认李伟"},
    ]}), encoding="utf-8")
    confirm(str(attendance_path), str(roster_path), str(candidate_path), str(matches_path), str(request_path))

    refreshed = build(str(attendance_path), str(roster_path), str(candidate_path), existing_path=str(matches_path))
    assert [row["payroll_person_id"] for row in refreshed["matches"]] == [41, 42]
    assert [row["user_confirmation"]["note"] for row in refreshed["matches"]] == ["确认张伟", "确认李伟"]


def test_duplicate_attendance_record_ids_rejected(tmp_path):
    source = attendance(count=2)
    source["people"][1]["record_id"] = source["people"][0]["record_id"]
    with pytest.raises(ValueError, match="record_id/name 缺失或 record_id 重复"):
        build_to_file(tmp_path, source=source)


def test_candidate_response_rejects_duplicate_client_ref(tmp_path):
    source = attendance()
    one = {"client_ref": "doc-1-p1-r1", "candidates": [candidate()]}
    with pytest.raises(ValueError, match="未知或重复"):
        build_to_file(tmp_path, source=source, candidate_rows=[one, copy.deepcopy(one)])
