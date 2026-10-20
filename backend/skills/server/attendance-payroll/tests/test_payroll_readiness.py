from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import payroll_readiness as readiness  # noqa: E402


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _inputs(tmp_path: Path, count: int, unmatched: set[int] | None = None):
    unmatched = unmatched or set()
    attendance = {
        "schema_version": 1,
        "month": "2026-06",
        "people": [
            {"record_id": f"rec-{index}", "name": f"人员{index}"}
            for index in range(count)
        ],
    }
    attendance_path = _write(tmp_path / "attendance.json", attendance)
    attendance_sha = hashlib.sha256(attendance_path.read_bytes()).hexdigest()
    matches = {
        "schema_version": 1,
        "attendance_sha256": attendance_sha,
        "matches": [
            {
                "record_id": f"rec-{index}",
                "status": "unmatched" if index in unmatched else "matched",
                "payroll_person_id": None if index in unmatched else 1000 + index,
                "roster_id": None if index in unmatched else 2000 + index,
                "match_method": None if index in unmatched else "active_roster_unique",
                "reason": "合成有效花名册匹配",
            }
            for index in range(count)
        ],
    }
    matches_path = _write(tmp_path / "person-matches.json", matches)
    return attendance_path, matches_path, attendance, matches


def _response(person_ids: list[int], statuses: list[str] | None = None, month: str = "2026-06"):
    statuses = statuses or ["COVERED"] * len(person_ids)
    items = []
    for pid, status in zip(person_ids, statuses, strict=True):
        items.append({
            "payroll_person_id": pid,
            "status": status,
            "source_month": "2026-05" if status == "COVERED" else None,
            "reason_code": "" if status == "COVERED" else f"{status}_REASON",
        })
    return {
        "payroll_month": month,
        "total_count": len(person_ids),
        "covered_count": statuses.count("COVERED"),
        "missing_count": statuses.count("MISSING_HISTORY"),
        "ambiguous_count": statuses.count("AMBIGUOUS_HISTORY"),
        "unknown_count": statuses.count("UNKNOWN"),
        "items": items,
    }


@pytest.mark.parametrize(
    ("total", "matched", "covered"),
    [(33, 25, 20), (42, 39, 31)],
)
def test_f31_synthetic_identity_coverage_scope_samples(
    tmp_path: Path, total: int, matched: int, covered: int,
):
    unmatched = set(range(matched, total))
    attendance, matches, _, _ = _inputs(tmp_path, total, unmatched=unmatched)
    ids = list(range(1000, 1000 + matched))
    response_path = _write(
        tmp_path / "response.json",
        _response(ids, ["COVERED"] * covered + ["MISSING_HISTORY"] * (matched - covered)),
    )

    report = readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path))

    assert report["counts"] == {
        "requested": matched,
        "covered": covered,
        "missing_history": matched - covered,
        "ambiguous_history": 0,
        "unknown": 0,
        "identity_not_in_scope": total - matched,
        "excluded_by_user_scope": 0,
    }
    assert len(report["items"]) == matched
    eligible = readiness._default_calculable_scope(report)
    assert eligible["count"] == covered
    expected_records = sorted(f"rec-{index}" for index in range(covered))
    assert eligible["record_ids"] == expected_records
    assert eligible["payroll_person_ids"] == [
        1000 + int(record_id.removeprefix("rec-")) for record_id in expected_records
    ]
    assert eligible["attendance_sha256"] == report["attendance_sha256"]
    assert eligible["person_matches_sha256"] == report["person_matches_sha256"]
    assert report["is_authorization"] is False
    assert report["is_payroll_receipt"] is False
    assert report["is_formal_precheck"] is False


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["COVERED"] * 3, (3, 0, 0, 0)),
        (["MISSING_HISTORY"] * 3, (0, 3, 0, 0)),
        (["AMBIGUOUS_HISTORY", "UNKNOWN", "COVERED"], (1, 0, 1, 1)),
    ],
)
def test_all_readiness_states_are_counted_without_guessing(tmp_path: Path, statuses: list[str], expected: tuple[int, ...]):
    attendance, matches, _, _ = _inputs(tmp_path, 3)
    response_path = _write(tmp_path / "response.json", _response([1000, 1001, 1002], statuses))

    report = readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path))

    assert (
        report["counts"]["covered"], report["counts"]["missing_history"],
        report["counts"]["ambiguous_history"], report["counts"]["unknown"],
    ) == expected


def test_identity_pending_and_duplicate_names_keep_distinct_record_and_person_ids(tmp_path: Path):
    attendance, matches, attendance_data, match_data = _inputs(tmp_path, 3, unmatched={1})
    attendance_data["people"][0]["name"] = "同名人员"
    attendance_data["people"][2]["name"] = "同名人员"
    _write(attendance, attendance_data)
    match_data["attendance_sha256"] = hashlib.sha256(attendance.read_bytes()).hexdigest()
    match_data["matches"][0]["payroll_person_id"] = 700
    match_data["matches"][2]["payroll_person_id"] = 701
    match_data["matches"][0]["roster_id"] = 700
    match_data["matches"][2]["roster_id"] = 700
    _write(matches, match_data)
    response_path = _write(tmp_path / "response.json", _response([700, 701]))

    report = readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path))

    assert report["counts"]["requested"] == 2
    assert report["counts"]["identity_not_in_scope"] == 1
    assert report["identity_not_in_scope"][0]["record_id"] == "rec-1"
    assert [item["payroll_person_id"] for item in report["items"]] == [700, 701]


def test_user_exact_scope_is_only_a_check_scope_not_authorization(tmp_path: Path):
    attendance, matches, _, _ = _inputs(tmp_path, 3)
    response_path = _write(tmp_path / "response.json", _response([1000]))
    record_ids_path = _write(tmp_path / "selected.json", ["rec-0"])

    report = readiness.build_report(
        str(attendance), str(matches), "2026-06", str(response_path), str(record_ids_path)
    )

    assert report["scope_source"] == "explicit_record_ids"
    assert report["counts"]["requested"] == 1
    assert report["counts"]["excluded_by_user_scope"] == 2
    assert report["is_authorization"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(payroll_month="2026-05"),
        lambda r: r.update(total_count=9),
        lambda r: r.update(covered_count=0),
        lambda r: r["items"].append(r["items"][0]),
        lambda r: r["items"].__setitem__(0, {**r["items"][0], "payroll_person_id": 9999}),
        lambda r: r["items"].pop(),
        lambda r: r["items"].__setitem__(0, {**r["items"][0], "source_month": "2026-07"}),
        lambda r: r["items"].__setitem__(0, {**r["items"][0], "status": "MISSING_HISTORY", "source_month": "2026-05"}),
        lambda r: r["items"].__setitem__(0, {**r["items"][0], "source_month": "not-a-month"}),
        lambda r: r["items"].__setitem__(0, {**r["items"][0], "status": "NOT_A_STATUS"}),
    ],
)
def test_malformed_or_inconsistent_mcp_result_fails_closed(tmp_path: Path, mutate):
    attendance, matches, _, _ = _inputs(tmp_path, 2)
    response = _response([1000, 1001])
    mutate(response)
    response_path = _write(tmp_path / "response.json", response)

    with pytest.raises(readiness.ReadinessError):
        readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path))


def test_month_mismatch_stale_matches_and_duplicate_payroll_id_fail_closed(tmp_path: Path):
    attendance, matches, attendance_data, match_data = _inputs(tmp_path, 2)
    response = _write(tmp_path / "response.json", _response([1000, 1001]))
    with pytest.raises(readiness.ReadinessError, match="ATTENDANCE_MONTH_MISMATCH"):
        readiness.build_report(str(attendance), str(matches), "2026-05", str(response))

    match_data["matches"][1]["payroll_person_id"] = 1000
    _write(matches, match_data)
    with pytest.raises(readiness.ReadinessError, match="PAYROLL_PERSON_ID_MAPPED_TO_MULTIPLE_RECORDS"):
        readiness.build_report(str(attendance), str(matches), "2026-06", str(response))

    match_data["matches"][1]["payroll_person_id"] = 1001
    _write(matches, match_data)
    attendance_data["people"][0]["name"] = "已更改"
    _write(attendance, attendance_data)
    with pytest.raises(readiness.ReadinessError, match="PERSON_MATCHES_ATTENDANCE_STALE"):
        readiness.build_report(str(attendance), str(matches), "2026-06", str(response))


def test_unavailable_is_never_ready_and_overwrites_prior_result(tmp_path: Path):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    response_path = _write(tmp_path / "response.json", _response([1000]))
    report_path = tmp_path / ".attendance-work" / "payroll-readiness.json"
    readiness._atomic_write(report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path)))

    result = readiness.write_unavailable(str(attendance), str(matches), "2026-06", str(report_path), "MCP_TIMEOUT")

    assert result["status"] == "UNAVAILABLE"
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "UNAVAILABLE"


def test_unavailable_can_be_recorded_when_no_payroll_identity_is_linked(tmp_path: Path, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 2, unmatched={0, 1})
    result = readiness.main([
        "request", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06"
    ])
    request = json.loads(capsys.readouterr().out)
    assert result == 0
    assert request["status"] == "IDENTITY_PENDING"
    assert request["mcp_request"] is None
    assert len(request["identity_not_in_scope"]) == 2

    report_path = tmp_path / ".attendance-work" / "payroll-readiness.json"
    report = readiness.write_unavailable(
        str(attendance), str(matches), "2026-06", str(report_path), "IDENTITY_NOT_READY"
    )
    assert report["status"] == "UNAVAILABLE"


def test_invalid_fresh_response_invalidates_prior_coverage_report(tmp_path: Path, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    good_response = _write(tmp_path / "good.json", _response([1000]))
    bad_response = _write(tmp_path / "bad.json", {"error": "timeout"})
    report_path = tmp_path / ".attendance-work" / "payroll-readiness.json"
    readiness._atomic_write(report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(good_response)))

    result = readiness.main([
        "check", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06",
        "--response", str(bad_response), "--output", str(report_path),
    ])

    assert result == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert readiness._read(report_path)[0]["status"] == "UNAVAILABLE"


def test_report_stales_when_attendance_or_identity_mapping_changes(tmp_path: Path):
    attendance, matches, attendance_data, match_data = _inputs(tmp_path, 2)
    response_path = _write(tmp_path / "response.json", _response([1000, 1001]))
    report_path = tmp_path / "payroll-readiness.json"
    readiness._atomic_write(report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path)))
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["ok"] is True

    attendance_data["people"][0]["name"] = "变更人员"
    _write(attendance, attendance_data)
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "READINESS_STALE"

    attendance_data["people"][0]["name"] = "人员0"
    _write(attendance, attendance_data)
    match_data["matches"][0]["reason"] = "mapping changed"
    _write(matches, match_data)
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "READINESS_STALE"


def test_record_scope_change_requires_fresh_query(tmp_path: Path):
    attendance, matches, _, _ = _inputs(tmp_path, 2)
    full_response = _write(tmp_path / "response.json", _response([1000, 1001]))
    report_path = tmp_path / "payroll-readiness.json"
    readiness._atomic_write(report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(full_response)))
    record_ids_path = _write(tmp_path / "selected.json", ["rec-0"])

    status = readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06", str(record_ids_path))

    assert status == {"ok": False, "status": "READINESS_STALE"}


def _write_valid_report(tmp_path: Path, count: int = 2):
    tmp_path.mkdir(parents=True, exist_ok=True)
    attendance, matches, _, _ = _inputs(tmp_path, count)
    response = _write(tmp_path / "response.json", _response(list(range(1000, 1000 + count))))
    report_path = tmp_path / ".attendance-work" / "payroll-readiness.json"
    readiness._atomic_write(
        report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(response))
    )
    return attendance, matches, report_path


def test_valid_report_status_checks_internal_counts_and_summary(tmp_path: Path):
    attendance, matches, report = _write_valid_report(tmp_path)
    status = readiness.report_status(str(report), str(attendance), str(matches), "2026-06")
    assert status["ok"] is True
    assert status["status"] == "COVERAGE_CHECKED"
    assert status["payroll_response_sha256_verified"] is False
    assert status["default_calculable_scope"]["count"] == 2


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["counts"].update(covered=1),
        lambda r: r["counts"].update(missing_history=1),
        lambda r: r["items"][0].update(status="MISSING_HISTORY", source_month=None),
        lambda r: r["items"].pop(),
        lambda r: r["items"][1].update(payroll_person_id=r["items"][0]["payroll_person_id"]),
        lambda r: r["items"][0].update(record_id="other-record"),
        lambda r: r["items"][0].update(source_month="2026-07"),
        lambda r: r["payroll_response_summary"]["items"][0].update(status="UNKNOWN"),
        lambda r: r["payroll_response_summary"]["items"][0].update(payroll_person_id=9999),
        lambda r: r.update(payroll_response_sha256="not-a-digest"),
        lambda r: r.update(normalized_response_sha256="0" * 64),
        lambda r: r.pop("scope_source"),
        lambda r: r.update(rules_version="old"),
        lambda r: r.update(attendance_sha256="0" * 64),
        lambda r: r.update(person_matches_sha256="0" * 64),
        lambda r: r.update(selected_record_ids=["rec-0"]),
        lambda r: r.update(identity_not_in_scope=[{"record_id": "rec-0", "name": "人员0", "status": "unmatched"}]),
        lambda r: r.update(scope_excluded_records=[{"record_id": "rec-0", "name": "人员0"}]),
    ],
)
def test_report_status_rejects_tampered_content(tmp_path: Path, mutate):
    attendance, matches, report_path = _write_valid_report(tmp_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    mutate(report)
    _write(report_path, report)

    status = readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")

    assert status["ok"] is False
    assert status["status"] in {"READINESS_REPORT_INVALID", "READINESS_STALE"}


@pytest.mark.parametrize("broken", ["attendance", "matches", "attendance_missing", "matches_missing"])
def test_check_failure_records_unavailable_without_reparsing_broken_inputs(tmp_path: Path, broken: str, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    response = _write(tmp_path / "response.json", {"not": "valid response"})
    report_path = tmp_path / ".attendance-work" / "payroll-readiness.json"
    good_response = _write(tmp_path / "good.json", _response([1000]))
    readiness._atomic_write(
        report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(good_response))
    )
    if broken.startswith("attendance"):
        if broken.endswith("missing"):
            attendance.unlink()
        else:
            attendance.write_text("{broken", encoding="utf-8")
    else:
        if broken.endswith("missing"):
            matches.unlink()
        else:
            matches.write_text("{broken", encoding="utf-8")

    result = readiness.main([
        "check", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06",
        "--response", str(response), "--output", str(report_path),
    ])

    assert result == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert readiness._read(report_path)[0]["status"] == "UNAVAILABLE"
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "UNAVAILABLE"


def test_unavailable_does_not_read_inputs_and_creates_directory(tmp_path: Path):
    report_path = tmp_path / "new" / "nested" / "report.json"
    report = readiness.write_unavailable(
        str(tmp_path / "missing-attendance"), str(tmp_path / "missing-matches"),
        "2026-06", str(report_path), "MCP_TIMEOUT",
    )
    assert report["status"] == "UNAVAILABLE"
    assert report["business_inputs_revalidated"] is False
    assert report_path.exists()


def test_missing_mcp_response_invalidates_old_report(tmp_path: Path, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    good_response = _write(tmp_path / "good.json", _response([1000]))
    report_path = tmp_path / "report.json"
    readiness._atomic_write(
        report_path, readiness.build_report(str(attendance), str(matches), "2026-06", str(good_response))
    )
    result = readiness.main([
        "check", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06",
        "--response", str(tmp_path / "missing-response.json"), "--output", str(report_path),
    ])
    assert result == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert readiness._read(report_path)[0]["status"] == "UNAVAILABLE"


def test_check_reports_unavailable_write_failure_and_never_success(tmp_path: Path, monkeypatch, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    response = _write(tmp_path / "bad.json", {"error": "no"})
    output = tmp_path / "report.json"
    monkeypatch.setattr(readiness, "_atomic_write", lambda *_: (_ for _ in ()).throw(OSError("disk")))

    result = readiness.main([
        "check", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06",
        "--response", str(response), "--output", str(output),
    ])

    assert result == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "UNAVAILABLE_STATE_WRITE_FAILED" in payload["error"]


def test_success_report_write_failure_attempts_to_invalidate_old_report(tmp_path: Path, monkeypatch, capsys):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    response = _write(tmp_path / "good.json", _response([1000]))
    output = tmp_path / "report.json"
    readiness._atomic_write(output, readiness.build_report(str(attendance), str(matches), "2026-06", str(response)))
    original_write = readiness._atomic_write
    writes = 0

    def fail_once(path, value):
        nonlocal writes
        writes += 1
        if writes == 1:
            raise OSError("transient replace failure")
        original_write(path, value)

    monkeypatch.setattr(readiness, "_atomic_write", fail_once)
    result = readiness.main([
        "check", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06",
        "--response", str(response), "--output", str(output),
    ])

    assert result == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
    assert readiness._read(output)[0]["status"] == "UNAVAILABLE"


def test_report_status_returns_structured_failure_for_corrupt_report_and_inputs(tmp_path: Path):
    attendance, matches, _, _ = _inputs(tmp_path, 1)
    report_path = _write(tmp_path / "bad-report.json", {"incomplete": True})
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "READINESS_REPORT_INVALID"
    report_path.write_text("broken", encoding="utf-8")
    assert readiness.report_status(str(report_path), str(attendance), str(matches), "2026-06")["status"] == "READINESS_REPORT_INVALID"

    valid_report = _write_valid_report(tmp_path / "valid", count=1)[2]
    attendance.write_text("broken", encoding="utf-8")
    status = readiness.report_status(str(valid_report), str(attendance), str(matches), "2026-06")
    assert status == {"ok": False, "status": "READINESS_CHECK_BLOCKED"}


def test_atomic_replace_failure_is_not_reported_as_success(tmp_path: Path, monkeypatch):
    report_path = tmp_path / "out" / "report.json"
    monkeypatch.setattr(readiness.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace")))
    with pytest.raises(OSError):
        readiness.write_unavailable("missing", "missing", "2026-06", str(report_path), "FAIL")


def test_unavailable_cli_failure_write_returns_blocked(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "_atomic_write", lambda *_: (_ for _ in ()).throw(OSError("permission")))
    result = readiness.main([
        "unavailable", "--attendance", "missing", "--matches", "missing", "--month", "2026-06",
        "--reason", "MCP_TIMEOUT", "--output", str(tmp_path / "x.json"),
    ])
    assert result == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_unmatched_and_non_selected_records_cannot_be_silently_dropped(tmp_path: Path):
    attendance, matches, _, _ = _inputs(tmp_path, 3, unmatched={2})
    response_path = _write(tmp_path / "response.json", _response([1000, 1001]))
    report = readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path))
    assert report["counts"]["identity_not_in_scope"] == 1
    assert report["identity_not_in_scope"][0]["record_id"] == "rec-2"

    record_ids_path = _write(tmp_path / "invalid-selection.json", ["rec-0", "rec-2"])
    with pytest.raises(readiness.ReadinessError, match="SELECTED_RECORDS_NOT_ALL_RELIABLY_MATCHED"):
        readiness.build_report(str(attendance), str(matches), "2026-06", str(response_path), str(record_ids_path))


def test_cli_help_exposes_only_local_validation_commands():
    assert "check_historical_salary_readiness" in readiness.__doc__
    assert "never calls Payroll" in readiness.__doc__


def test_request_builder_uses_exact_current_person_ids_and_does_not_infer_roster_id(tmp_path: Path, capsys):
    attendance, matches, _, match_data = _inputs(tmp_path, 2)
    match_data["matches"][0]["payroll_person_id"] = 8001
    match_data["matches"][0]["roster_id"] = 43
    match_data["matches"][1]["payroll_person_id"] = 8002
    match_data["matches"][1]["roster_id"] = 43
    _write(matches, match_data)

    result = readiness.main([
        "request", "--attendance", str(attendance), "--matches", str(matches), "--month", "2026-06"
    ])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mcp_request"] == {"payroll_month": "2026-06", "payroll_person_ids": [8001, 8002]}
    assert payload["mcp_request"]["payroll_person_ids"] != [43]
    assert payload["is_authorization"] is False


def test_payroll_stage_keeps_batch_guards_and_separate_authorizations():
    reference = (Path(__file__).resolve().parents[1] / "references" / "payroll-processing.md").read_text()
    assert "新 Task ID 或单条 Operation 查询无记录都不能证明不存在其他相关批次" in reference
    assert "若已有提交回执，原批次人员范围已固定，不得缩围、扩围或换 Batch ID" in reference
    assert "正式 Payroll `precheck_payroll`" in reference
    assert "`valid=true`" in reference
    assert "正式考勤提交授权" in reference
    assert "另行明确授权工资核算" in reference
    assert "工具缺失、超时、错误" in reference
