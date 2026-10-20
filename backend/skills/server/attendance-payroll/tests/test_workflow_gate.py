from __future__ import annotations

import json
import hashlib
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workflow_gate  # noqa: E402
import payroll_readiness  # noqa: E402
import project_binding  # noqa: E402


def _binding_request(prepared: dict, bindings: list[dict], confirmation: str) -> dict:
    bindings = sorted(bindings, key=lambda row: row["source_project_name"])
    mapping_sha = hashlib.sha256(json.dumps(
        bindings, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    display = (f"考勤月份：{prepared['month']}\n考勤人数：2 人\n项目对应关系：\n" + "\n".join(
        f"来源项目：{row['source_project_name']} → Payroll 项目：{row['payroll_project_name']}"
        for row in bindings
    ) + "\n请确认考勤事实及以上项目对应关系。")
    display_sha = hashlib.sha256(display.encode("utf-8")).hexdigest()
    confirmation_sha = hashlib.sha256(confirmation.encode("utf-8")).hexdigest()
    return {
        "month": prepared["month"], "attendance_sha256": prepared["attendance_sha256"],
        "candidate_response_sha256": prepared["candidate_response_sha256"], "bindings": bindings,
        "display_evidence": {
            "message_index": 0, "message": display, "message_sha256": display_sha,
            "month": prepared["month"], "attendance_sha256": prepared["attendance_sha256"],
            "candidate_response_sha256": prepared["candidate_response_sha256"],
            "bindings": bindings, "mapping_sha256": mapping_sha,
        },
        "user_confirmation": {"message_index": 1, "message": confirmation,
                              "message_sha256": confirmation_sha},
        "conversation_messages": [
            {"index": 0, "role": "assistant", "content": display},
            {"index": 1, "role": "user", "content": confirmation},
        ],
    }


TEST_ATTENDANCE_DIR = tempfile.TemporaryDirectory(prefix="workflow-gate-")
BATCH = "task_A12-2026-06"
TEST_ATTENDANCE_PATH = Path(TEST_ATTENDANCE_DIR.name) / "attendance.json"
TEST_WORK_DIR = TEST_ATTENDANCE_PATH.parent / ".attendance-work"
TEST_WORK_DIR.mkdir(exist_ok=True)
TEST_ATTENDANCE_DATA = {"schema_version": 1, "month": "2026-06", "people": [
    {"record_id": "rec-1", "name": "安娜", "project": "合成项目"},
    {"record_id": "rec-2", "name": "李明", "project": "合成项目"},
]}
TEST_ATTENDANCE_PATH.write_text(json.dumps(TEST_ATTENDANCE_DATA, ensure_ascii=False), encoding="utf-8")
TEST_ROSTER_PATH, TEST_BINDING_PATH = project_binding.default_paths(TEST_ATTENDANCE_PATH)
TEST_ROSTER_PATH.write_text(json.dumps({"count": 1, "items": [{
    "roster_id": 10, "name": "安娜", "project_name": "合成项目", "company_name": "合成公司",
    "employee_type": 1, "position": "施工员",
}]}, ensure_ascii=False), encoding="utf-8")
TEST_BINDING_PREPARED = project_binding.prepare(TEST_ATTENDANCE_PATH, TEST_ROSTER_PATH)
TEST_BINDING_REQUEST = TEST_WORK_DIR / "project-binding-request.json"
TEST_BINDING_REQUEST.write_text(json.dumps(_binding_request(
    TEST_BINDING_PREPARED, [{"source_project_name": "合成项目", "payroll_project_name": "合成项目"}],
    "确认合成项目对应合成项目",
), ensure_ascii=False), encoding="utf-8")
TEST_BINDING = project_binding.confirm(
    TEST_ATTENDANCE_PATH, TEST_ROSTER_PATH, TEST_BINDING_REQUEST, TEST_BINDING_PATH,
)
TEST_MATCHES_PATH = TEST_WORK_DIR / "person-matches.json"
TEST_MATCHES = {"schema_version": 1, "attendance_sha256": TEST_BINDING["attendance_sha256"],
                "project_binding_sha256": TEST_BINDING["binding_sha256"], "matches": [
                    {"record_id": "rec-1", "status": "matched", "payroll_person_id": 1},
                    {"record_id": "rec-2", "status": "matched", "payroll_person_id": 2},
                ]}
TEST_MATCHES_PATH.write_text(json.dumps(TEST_MATCHES), encoding="utf-8")
TEST_SUBMISSION_PATH = TEST_WORK_DIR / "submission-request.json"
TEST_SUBMISSION_PATH.write_text(json.dumps({
    "attendance_month": "2026-06", "submission_mode": "BATCH_SNAPSHOT", "batch_id": BATCH,
    "operation_id": f"submit:{BATCH}", "records": [
        {"payroll_person_id": 1, "source_project_snapshot": "合成项目", "project_snapshot": "合成项目"},
        {"payroll_person_id": 2, "source_project_snapshot": "合成项目", "project_snapshot": "合成项目"},
    ],
}, ensure_ascii=False), encoding="utf-8")
TEST_ATTENDANCE_SHA256 = hashlib.sha256(TEST_ATTENDANCE_PATH.read_bytes()).hexdigest()

SCOPE = {
    "month": "2026-06", "version": "review-v5", "attendance_sha256": TEST_ATTENDANCE_SHA256,
    "record_ids": ["rec-1", "rec-2"],
}
PEOPLE = [
    {"record_id": "rec-1", "name": "安娜"},
    {"record_id": "rec-2", "name": "李明"},
]


def _operation_state(submission: str, calculation: str, scope: dict = SCOPE, batch_id: str = BATCH,
                     payroll_person_ids: list[int] | None = None):
    payroll_person_ids = payroll_person_ids or [1, 2]

    def item(kind: str, status: str):
        operation = {"operation_id": f"{kind}:{batch_id}", "status": status}
        if status == "SUCCEEDED":
            operation.update({key: scope[key] for key in ("month", "attendance_sha256", "record_ids")})
            operation["payroll_person_ids"] = payroll_person_ids
        return operation

    return {
        "status": "VERIFIED", "task_id": "task_A12", "batch_id": batch_id,
        "month": scope["month"],
        "operations": {
            "submission": item("submit", submission),
            "calculation": item("calculate", calculation),
        },
    }


def _evidence():
    return {
        "attendance_path": str(TEST_ATTENDANCE_PATH),
        "person_matches_path": str(TEST_MATCHES_PATH),
        "submission_request_path": str(TEST_SUBMISSION_PATH),
        "attendance_review": {
            "status": "DECLARED", **SCOPE, "people": PEOPLE,
            "visible_after_user_message_index": 0,
        },
        "identity_matching": {"status": "COMPLETE", **SCOPE, "people": PEOPLE},
        "salary_readiness": {"status": "COVERAGE_CHECKED", **SCOPE, "people": PEOPLE},
        "submission_scope_review": {
            "status": "CONFIRMED", **SCOPE, "people": PEOPLE, "confirmation_message_index": 0,
        },
        "batch_context": {
            "status": "VERIFIED_NO_CONFLICT", "task_id": "task_A12", "batch_id": BATCH,
            "operation_id": f"submit:{BATCH}", **SCOPE, "payroll_person_ids": [1, 2],
        },
        "submission_receipt": {
            "status": "SUCCEEDED", **SCOPE, "batch_id": BATCH, "operation_id": f"submit:{BATCH}",
        },
        "payroll_precheck": {
            "status": "VALID", "valid": True, **SCOPE, "people": PEOPLE,
            "batch_id": BATCH, "operation_id": f"precheck:{BATCH}",
        },
        "calculation_receipt": {
            "status": "SUCCEEDED", **SCOPE, "batch_id": BATCH, "operation_id": f"calculate:{BATCH}",
        },
        "payroll_operation_state": _operation_state("SUCCEEDED", "SUCCEEDED"),
    }


def _request(action: str, message: str, *prior: str):
    evidence = _evidence()
    if action == "ATTENDANCE_SUBMISSION":
        evidence["payroll_operation_state"] = _operation_state("NOT_FOUND", "NOT_FOUND")
    elif action in {"PAYROLL_PRECHECK", "PAYROLL_CALCULATION"}:
        evidence["payroll_operation_state"] = _operation_state("SUCCEEDED", "NOT_FOUND")
    return {"action": action, "user_messages": [*prior, message], "evidence": evidence,
            "expected_submit_operation_id": f"submit:{BATCH}",
            "expected_precheck_operation_id": f"precheck:{BATCH}",
            "expected_calculate_operation_id": f"calculate:{BATCH}"}


def _auth_text(intent: str) -> str:
    return f"我{intent}2026-06版本review-v5的安娜和李明。"


def _confirmed(index: int = 1):
    return {"status": "CONFIRMED_FOR_CURRENT_REVIEW", **SCOPE, "confirmation_message_index": index}


@pytest.mark.parametrize(
    ("task_prompt", "action"),
    [
        ("请识别考勤并生成核对表，等我确认。", "ATTENDANCE_REVIEW"),
        ("请核对考勤，确认前不得提交。", "ATTENDANCE_REVIEW"),
    ],
)
def test_0925_and_0929_initial_requests_admit_only_attendance_review(task_prompt: str, action: str):
    result = workflow_gate.evaluate({"action": action, "user_messages": [task_prompt], "evidence": {}})
    assert result["ok"] is True
    assert result["next_action"] == "DELIVER_ATTENDANCE_REVIEW_AND_STOP"

    submission = workflow_gate.evaluate(_request("ATTENDANCE_SUBMISSION", task_prompt))
    assert submission["ok"] is False


def test_attendance_confirmation_allows_only_explicitly_requested_readonly_followup():
    prior = "考勤确认后请匹配人员，并查询历史工资覆盖。"
    matching = workflow_gate.evaluate(_request("IDENTITY_MATCHING", "确认考勤", prior))
    readiness = workflow_gate.evaluate(_request("SALARY_READINESS", "确认考勤", prior))
    assert matching["ok"] is True
    assert matching["next_action"] == "MATCH_IDENTITIES_THEN_STOP_BEFORE_SUBMISSION"
    assert matching["attendance_confirmation_evidence"]["attendance_sha256"] == SCOPE["attendance_sha256"]
    assert readiness["ok"] is True
    assert readiness["next_action"] == "RUN_READ_ONLY_COVERAGE_CHECK_THEN_STOP"

    generic = workflow_gate.evaluate(_request("IDENTITY_MATCHING", "确认考勤"))
    assert generic["ok"] is False
    match_before_confirm = workflow_gate.evaluate(_request("IDENTITY_MATCHING", "请匹配人员", prior))
    assert match_before_confirm["ok"] is False


@pytest.mark.parametrize(("field", "value"), [
    ("source_project_snapshot", "猜测的来源项目"),
    ("project_snapshot", "未确认的 Payroll 项目"),
])
def test_submission_project_binding_mismatch_is_blocked_before_write(field: str, value: str):
    original = TEST_SUBMISSION_PATH.read_bytes()
    try:
        submission = json.loads(original)
        submission["records"][0][field] = value
        TEST_SUBMISSION_PATH.write_text(json.dumps(submission, ensure_ascii=False), encoding="utf-8")

        result = workflow_gate.evaluate(_request(
            "ATTENDANCE_SUBMISSION", _auth_text("授权正式提交考勤"),
            "本次处理范围为2026-06版本review-v5的安娜和李明。",
        ))

        assert result["ok"] is False
        assert result["error"] == "PROJECT_BINDING_SUBMISSION_PROJECT_MISMATCH"
    finally:
        TEST_SUBMISSION_PATH.write_bytes(original)


def test_cross_turn_identity_matching_uses_prior_confirmation_bound_to_current_review():
    request = _request("IDENTITY_MATCHING", "现在开始匹配人员", "请识别考勤并在我确认后匹配人员。", "确认考勤")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    result = workflow_gate.evaluate(request)
    assert result["ok"] is True
    assert result["attendance_confirmation_evidence"]["confirmation_message_index"] == 1
    assert result["message_source_verified"] is False


def test_reconfirmed_corrected_review_can_reenter_readonly_identity_matching(tmp_path: Path):
    request = _request(
        "IDENTITY_MATCHING", "现在开始匹配人员", "请识别考勤并在我确认后匹配人员。", "确认考勤",
    )
    attendance_path = tmp_path / "attendance.json"
    attendance_path.write_text('{"synthetic":"corrected-attendance"}\n', encoding="utf-8")
    scope = {**SCOPE, "version": "review-v6",
             "attendance_sha256": hashlib.sha256(attendance_path.read_bytes()).hexdigest()}
    request["evidence"]["attendance_path"] = str(attendance_path)
    request["evidence"]["attendance_review"].update(scope)
    request["evidence"]["attendance_confirmation"] = {
        "status": "CONFIRMED_FOR_CURRENT_REVIEW", **scope, "confirmation_message_index": 1,
    }

    result = workflow_gate.evaluate(request)
    assert result["ok"] is True
    assert result["attendance_confirmation_evidence"]["attendance_sha256"] == scope["attendance_sha256"]


def test_cross_turn_salary_readiness_uses_prior_confirmation_and_completed_identity():
    request = _request("SALARY_READINESS", "检查历史工资覆盖", "请识别考勤。", "确认考勤", "开始匹配人员")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    result = workflow_gate.evaluate(request)
    assert result["ok"] is True
    assert result["next_action"] == "RUN_READ_ONLY_COVERAGE_CHECK_THEN_STOP"


def test_original_task_salary_instruction_allows_readiness_after_confirm_and_matching():
    request = _request(
        "SALARY_READINESS", "现在检查历史工资覆盖", "考勤确认后匹配人员并检查历史工资覆盖。", "确认考勤",
    )
    request["user_messages"].append("人员匹配完成")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    assert workflow_gate.evaluate(request)["ok"] is True


def test_f31_original_payroll_intent_runs_readiness_after_matching_without_extra_user_prompt():
    request = _request(
        "SALARY_READINESS",
        "确认考勤",
        "请识别考勤；我确认后请匹配人员并自动检查历史工资覆盖。",
    )
    request["evidence"]["attendance_confirmation"] = _confirmed(index=1)

    result = workflow_gate.evaluate(request)

    assert result["ok"] is True
    assert result["next_action"] == "RUN_READ_ONLY_COVERAGE_CHECK_THEN_STOP"
    assert result["runtime_enforced"] is False


@pytest.mark.parametrize("change", ["digest", "version", "missing_version"])
def test_attendance_correction_or_old_review_invalidates_prior_confirmation(change: str):
    request = _request("IDENTITY_MATCHING", "开始匹配人员", "确认考勤")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    for key in ("attendance_review", "identity_matching"):
        if change == "digest":
            request["evidence"][key]["attendance_sha256"] = "b" * 64
        elif change == "version":
            request["evidence"][key]["version"] = "review-v4"
        else:
            request["evidence"][key].pop("version")
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] in {
        "ATTENDANCE_CONFIRMATION_STALE", "IDENTITY_SCOPE_MISMATCH",
        "ATTENDANCE_REVIEW_VERSION_REQUIRED", "ATTENDANCE_REVIEW_CONTENT_MISMATCH",
    }


def test_confirmation_before_review_visibility_and_unbound_confirmation_fail_closed():
    request = _request("IDENTITY_MATCHING", "开始匹配人员", "确认考勤")
    request["evidence"]["attendance_confirmation"] = _confirmed(index=0)
    assert workflow_gate.evaluate(request)["error"] == "ATTENDANCE_CONFIRMATION_NOT_AFTER_CURRENT_REVIEW"

    request["evidence"].pop("attendance_confirmation")
    assert workflow_gate.evaluate(request)["error"] == "ATTENDANCE_CONFIRMATION_REQUIRED"


def test_missing_current_attendance_content_digest_blocks_readonly_followup():
    request = _request("IDENTITY_MATCHING", "确认考勤", "请匹配人员")
    request["evidence"]["attendance_review"].pop("attendance_sha256")
    assert workflow_gate.evaluate(request)["ok"] is False


def test_current_attendance_file_must_match_review_digest():
    request = _request("IDENTITY_MATCHING", "确认考勤", "请匹配人员")
    request["evidence"]["attendance_path"] = str(TEST_ATTENDANCE_PATH.parent / "missing.json")
    assert workflow_gate.evaluate(request)["error"] == "CURRENT_ATTENDANCE_FILE_UNAVAILABLE"

    request = _request("IDENTITY_MATCHING", "确认考勤", "请匹配人员")
    request["evidence"]["attendance_path"] = ""
    assert workflow_gate.evaluate(request)["error"] == "CURRENT_ATTENDANCE_PATH_REQUIRED"


def test_continue_without_prior_followup_intent_does_not_auto_advance():
    request = _request("IDENTITY_MATCHING", "继续", "请识别考勤并等待确认。", "确认考勤")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    assert workflow_gate.evaluate(request)["error"] == "IDENTITY_MATCHING_NOT_EXPLICITLY_REQUESTED"


def test_readiness_requires_explicit_current_or_original_salary_intent():
    request = _request("SALARY_READINESS", "继续", "请识别并核对考勤。", "确认考勤")
    request["evidence"]["attendance_confirmation"] = _confirmed()
    assert workflow_gate.evaluate(request)["error"] == "SALARY_WORKFLOW_NOT_REQUESTED"


def test_controlled_attendance_correction_remains_in_review_stage():
    result = workflow_gate.evaluate(_request("ATTENDANCE_REVIEW", "请更正安娜6月8日的考勤标记。"))
    assert result["ok"] is True
    assert result["next_action"] == "APPLY_CONTROLLED_CORRECTION_REEXPORT_AND_STOP"


@pytest.mark.parametrize(
    ("action", "message"),
    [
        ("ATTENDANCE_SUBMISSION", "确认考勤"),
        ("ATTENDANCE_SUBMISSION", "人员匹配完成"),
        ("ATTENDANCE_SUBMISSION", "历史工资覆盖检查通过"),
        ("ATTENDANCE_SUBMISSION", "我认可本次范围2026-06版本review-v5的安娜和李明。"),
        ("ATTENDANCE_SUBMISSION", "继续处理"),
        ("ATTENDANCE_SUBMISSION", "开始工资核算"),
        ("ATTENDANCE_SUBMISSION", "生成工资表"),
        ("ATTENDANCE_SUBMISSION", "我不同意正式提交考勤。"),
        ("ATTENDANCE_SUBMISSION", "是否正式提交考勤2026-06版本review-v5的安娜和李明？"),
    ],
)
def test_non_submission_phrases_never_authorize_attendance_write(action: str, message: str):
    result = workflow_gate.evaluate(_request(action, message))
    assert result["ok"] is False
    assert result["status"] == "WORKFLOW_BLOCKED"


def test_exact_submission_intent_is_bound_to_month_version_and_people():
    result = workflow_gate.evaluate(_request(
        "ATTENDANCE_SUBMISSION", _auth_text("授权正式提交考勤"),
        "本次处理范围为2026-06版本review-v5的安娜和李明。",
    ))
    assert result["ok"] is True
    assert result["status"] == "WRITE_STAGE_ELIGIBLE"
    assert result["is_authorization_proof"] is False
    assert result["message_source_verified"] is False
    assert result["runtime_enforced"] is False
    assert result["authorization_text_checked"] is True


def test_payroll_write_stages_fail_closed_when_operation_state_is_missing_or_unknown():
    request = _execution_request(2, 2, 2)
    request["evidence"].pop("payroll_operation_state")
    assert workflow_gate.evaluate(request)["error"] == "PAYROLL_OPERATION_STATE_UNVERIFIED"

    request = _execution_request(2, 2, 2)
    request["evidence"]["payroll_operation_state"]["operations"]["submission"]["status"] = "UNKNOWN"
    assert workflow_gate.evaluate(request)["error"] == "PAYROLL_OPERATION_STATE_UNVERIFIED"


def test_changed_review_is_blocked_when_fixed_submit_operation_has_old_receipt():
    request = _request("ATTENDANCE_SUBMISSION", _auth_text("授权正式提交考勤"),
                       "本次处理范围为2026-06版本review-v5的安娜和李明。")
    state = request["evidence"]["payroll_operation_state"]
    state["operations"]["submission"] = _operation_state(
        "SUCCEEDED", "NOT_FOUND", {**SCOPE, "attendance_sha256": "f" * 64},
    )["operations"]["submission"]
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "ATTENDANCE_CORRECTION_AFTER_SUBMISSION_BLOCKED"


def test_changed_review_is_blocked_when_fixed_calculation_operation_has_old_result():
    request = _request("PAYROLL_CALCULATION", _auth_text("授权工资核算"))
    state = request["evidence"]["payroll_operation_state"]
    state["operations"]["calculation"] = _operation_state(
        "SUCCEEDED", "SUCCEEDED", {**SCOPE, "attendance_sha256": "f" * 64},
    )["operations"]["calculation"]
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "ATTENDANCE_CORRECTION_AFTER_CALCULATION_BLOCKED"


def test_same_scope_calculation_receipt_prevents_calculate_replay():
    request = _request("PAYROLL_CALCULATION", _auth_text("授权工资核算"))
    request["evidence"]["payroll_operation_state"] = _operation_state("SUCCEEDED", "SUCCEEDED")
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "PAYROLL_CALCULATION_ALREADY_EXISTS"


def test_prior_submission_or_calculation_blocks_new_execution_authorization():
    request = _execution_request(2, 2, 2)
    state = request["evidence"]["payroll_operation_state"]
    pids = request["evidence"]["batch_context"]["payroll_person_ids"]
    state["operations"]["submission"] = _operation_state(
        "SUCCEEDED", "NOT_FOUND", {**request["evidence"]["execution_scope"],
                                    "attendance_sha256": "f" * 64},
        payroll_person_ids=pids,
    )["operations"]["submission"]
    assert workflow_gate.evaluate(request)["error"] == "ATTENDANCE_CORRECTION_AFTER_SUBMISSION_BLOCKED"

    request = _execution_request(2, 2, 2)
    state = request["evidence"]["payroll_operation_state"]
    pids = request["evidence"]["batch_context"]["payroll_person_ids"]
    state["operations"]["calculation"] = _operation_state(
        "NOT_FOUND", "SUCCEEDED", {**request["evidence"]["execution_scope"],
                                    "attendance_sha256": "f" * 64},
        payroll_person_ids=pids,
    )["operations"]["calculation"]
    assert workflow_gate.evaluate(request)["error"] == "ATTENDANCE_CORRECTION_AFTER_CALCULATION_BLOCKED"


def test_precheck_cannot_reuse_submission_receipt_from_another_attendance_sha():
    request = _request("PAYROLL_PRECHECK", "开始正式预检查")
    request["evidence"]["payroll_operation_state"]["operations"]["submission"] = _operation_state(
        "SUCCEEDED", "NOT_FOUND", {**SCOPE, "attendance_sha256": "f" * 64},
    )["operations"]["submission"]
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "ATTENDANCE_CORRECTION_AFTER_SUBMISSION_BLOCKED"


def test_export_cannot_bind_old_calculation_to_current_attendance_review():
    request = _request("PAYROLL_EXPORT", "交付工资核算表")
    request["evidence"]["payroll_operation_state"]["operations"]["calculation"] = _operation_state(
        "SUCCEEDED", "SUCCEEDED", {**SCOPE, "attendance_sha256": "f" * 64},
    )["operations"]["calculation"]
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "ATTENDANCE_CORRECTION_AFTER_CALCULATION_BLOCKED"


def _execution_request(total: int, covered: int, matched: int | None = None, authorization: str | None = None):
    matched = matched if matched is not None else covered + 5
    work_dir = Path(TEST_ATTENDANCE_DIR.name) / ".attendance-work"
    work_dir.mkdir(exist_ok=True)
    attendance_path = work_dir / "attendance.json"
    matches_path = work_dir / "person-matches.json"
    report_path = work_dir / "payroll-readiness.json"
    attendance_data = {
        "schema_version": 1, "month": "2026-06",
        "people": [{"record_id": f"rec-{i:03d}", "name": f"人员{i:02d}", "project": "合成项目"}
                   for i in range(total)],
    }
    attendance_path.write_text(json.dumps(attendance_data, ensure_ascii=False), encoding="utf-8")
    attendance_sha = hashlib.sha256(attendance_path.read_bytes()).hexdigest()
    roster_path, binding_path = project_binding.default_paths(attendance_path)
    roster_path.write_text(json.dumps({"count": 1, "items": [{
        "roster_id": 2000, "name": "人员00", "project_name": "合成项目", "company_name": "合成公司",
        "employee_type": 1, "position": "施工员",
    }]}, ensure_ascii=False), encoding="utf-8")
    binding_prepared = project_binding.prepare(attendance_path, roster_path)
    binding_request_path = work_dir / "project-binding-request.json"
    binding_request_path.write_text(json.dumps(_binding_request(
        binding_prepared, [{"source_project_name": "合成项目", "payroll_project_name": "合成项目"}],
        "确认合成项目对应合成项目",
    ), ensure_ascii=False), encoding="utf-8")
    binding = project_binding.confirm(attendance_path, roster_path, binding_request_path, binding_path)
    attendance = {
        "month": "2026-06", "version": "review-exec-v1", "attendance_sha256": attendance_sha,
        "record_ids": [f"rec-{i:03d}" for i in range(total)],
    }
    people = [
        {"record_id": f"rec-{i:03d}", "name": f"人员{i:02d}",
         "status": "matched" if i < matched else "unmatched",
         "payroll_person_id": 1000 + i if i < matched else None}
        for i in range(total)
    ]
    matches_data = {
        "schema_version": 1, "attendance_sha256": attendance_sha,
        "project_binding_sha256": binding["binding_sha256"],
        "matches": [
            {"record_id": f"rec-{i:03d}", "status": "matched" if i < matched else "unmatched",
             "payroll_person_id": 1000 + i if i < matched else None,
             "roster_id": 2000 + i if i < matched else None,
             "match_method": "active_roster_unique" if i < matched else None}
            for i in range(total)
        ],
    }
    identity_raw = json.dumps(matches_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    identity_sha = hashlib.sha256(identity_raw).hexdigest()
    identity_path = matches_path
    identity_path.write_bytes(identity_raw)
    response_items = [
        {"payroll_person_id": 1000 + i, "status": "COVERED" if i < covered else "MISSING_HISTORY",
         "source_month": "2026-05" if i < covered else None,
         "reason_code": "" if i < covered else "MISSING_HISTORY"}
        for i in range(matched)
    ]
    response = {
        "payroll_month": "2026-06", "total_count": matched,
        "covered_count": covered, "missing_count": matched - covered,
        "ambiguous_count": 0, "unknown_count": 0, "items": response_items,
    }
    response_path = work_dir / "mcp-response.json"
    response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
    report = payroll_readiness.build_report(str(attendance_path), str(matches_path), "2026-06", str(response_path))
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    default = payroll_readiness._default_calculable_scope(report)
    items = report["items"]
    readiness_sha = report["normalized_response_sha256"]
    record_ids = default["record_ids"]
    selected_people = default["people"]
    selected = {
        **attendance, "record_ids": record_ids, "person_matches_sha256": identity_sha,
        "payroll_person_ids": default["payroll_person_ids"], "people": selected_people,
    }
    task_id = "task_A12"
    batch_id = f"{task_id}-2026-06"
    evidence = {
        "attendance_path": str(attendance_path),
        "person_matches_path": str(identity_path),
        "submission_request_path": str(work_dir / "submission-request.json"),
        "readiness_report_path": str(report_path),
        "attendance_review": {
            "status": "DECLARED", **attendance,
            "people": [{"record_id": p["record_id"], "name": p["name"]} for p in people],
            "visible_after_user_message_index": 0,
        },
        "attendance_confirmation": {
            "status": "CONFIRMED_FOR_CURRENT_REVIEW", **attendance,
            "confirmation_message_index": 1,
        },
        "identity_matching": {
            "status": "COMPLETE", **attendance, "people": people,
            "person_matches_sha256": identity_sha,
        },
        "salary_readiness": {
            "status": "COVERAGE_CHECKED", **attendance,
            "record_ids": report["selected_record_ids"],
            "person_matches_sha256": identity_sha,
            "normalized_response_sha256": readiness_sha, "items": items,
            "counts": report["counts"],
            "requested_payroll_person_ids": report["requested_payroll_person_ids"],
            "payroll_response_summary": report["payroll_response_summary"],
        },
        "execution_scope": selected,
        "batch_context": {
            "status": "VERIFIED_NO_CONFLICT", "task_id": task_id, "batch_id": batch_id,
            "operation_id": f"submit:{batch_id}", **{**selected, "record_ids": record_ids},
            "payroll_person_ids": default["payroll_person_ids"],
        },
        "payroll_operation_state": {
            "status": "VERIFIED", "task_id": task_id, "batch_id": batch_id, "month": "2026-06",
            "operations": {
                "submission": {"operation_id": f"submit:{batch_id}", "status": "NOT_FOUND"},
                "calculation": {"operation_id": f"calculate:{batch_id}", "status": "NOT_FOUND"},
            },
        },
    }
    submission_records = []
    for person in selected_people:
        index = int(person["record_id"].split("-")[1])
        submission_records.append({
            "payroll_person_id": 1000 + index,
            "source_project_snapshot": "合成项目",
            "project_snapshot": "合成项目",
        })
    Path(evidence["submission_request_path"]).write_text(json.dumps({
        "attendance_month": "2026-06", "submission_mode": "BATCH_SNAPSHOT", "batch_id": batch_id,
        "operation_id": f"submit:{batch_id}", "records": submission_records,
    }, ensure_ascii=False), encoding="utf-8")
    scope_sha = workflow_gate._scope_digest(
        {**attendance, "record_ids": record_ids}, identity_sha,
        [1000 + i for i in range(covered)], readiness_sha,
    )
    included = "、".join(person["name"] for person in selected_people)
    excluded = "；".join(
        f"{item['name']}：{('身份待核实' if item['status'] == 'unmatched' else '缺少历史工资')}"
        for item in people[matched:]
    )
    # Include all mapped people excluded due to missing history as well.
    excluded = "；".join(
        f"{p['name']}：{('身份待核实' if p['status'] == 'unmatched' else '缺少历史工资')}"
        for p in people if p["record_id"] not in record_ids
    )
    display = (
        f"工资核算范围：2026-06，共{covered}人。纳入：{included}。排除事项：{excluded}。"
        "后续将正式提交考勤、执行正式预检查，并在通过后进行工资核算。"
    )
    conversation = [
        {"role": "user", "content": "请识别考勤，确认后匹配并检查历史工资覆盖。"},
        {"role": "assistant", "content": "考勤确认表已交付。"},
        {"role": "user", "content": "确认考勤"},
        {"role": "assistant", "content": display},
        {"role": "user", "content": authorization or f"按刚才展示的{covered}人开始工资核算。"},
    ]
    evidence["scope_display"] = {"message_index": 3, "scope_sha256": scope_sha}
    return {
        "action": "PAYROLL_EXECUTION",
        "user_messages": [conversation[i]["content"] for i in (0, 2, 4)],
        "conversation_messages": conversation,
        "evidence": evidence,
        "expected_submit_operation_id": f"submit:{batch_id}",
        "expected_precheck_operation_id": f"precheck:{batch_id}",
        "expected_calculate_operation_id": f"calculate:{batch_id}",
    }


def _with_confirmed_conflict_exclusion(request: dict, record_index: int = 25) -> dict:
    evidence = request["evidence"]
    work_dir = Path(evidence["readiness_report_path"]).parent
    identity_path = Path(evidence["person_matches_path"])
    matches_data = json.loads(identity_path.read_text(encoding="utf-8"))
    record_id = f"rec-{record_index:03d}"
    match = next(row for row in matches_data["matches"] if row["record_id"] == record_id)
    match["status"] = "ambiguous"
    match["facts"] = {"name": f"人员{record_index:02d}"}
    identity_raw = json.dumps(matches_data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    identity_path.write_bytes(identity_raw)
    identity_sha = hashlib.sha256(identity_raw).hexdigest()
    evidence["identity_matching"]["person_matches_sha256"] = identity_sha
    evidence["identity_matching"]["people"][record_index]["status"] = "ambiguous"
    evidence["execution_scope"]["person_matches_sha256"] = identity_sha
    evidence["batch_context"]["person_matches_sha256"] = identity_sha

    report = payroll_readiness.build_report(
        str(work_dir / "attendance.json"), str(identity_path), "2026-06", str(work_dir / "mcp-response.json"),
    )
    Path(evidence["readiness_report_path"]).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    evidence["salary_readiness"].update({
        "person_matches_sha256": identity_sha,
        "normalized_response_sha256": report["normalized_response_sha256"],
        "items": report["items"], "counts": report["counts"],
        "requested_payroll_person_ids": report["requested_payroll_person_ids"],
        "payroll_response_summary": report["payroll_response_summary"],
    })

    user_text = f"人员{record_index:02d}暂不纳入本次工资核算"
    reason = "同名候选存在跨项目冲突"
    conversation = request["conversation_messages"]
    old_display = conversation[3]["content"]
    old_display = old_display.replace(
        f"人员{record_index:02d}：身份待核实",
        f"人员{record_index:02d}：用户确认本次暂不纳入：{reason}",
    )
    conversation[3:3] = [
        {"role": "assistant", "content": "人员身份存在待核实事项。"},
        {"role": "user", "content": user_text},
    ]
    conversation[5]["content"] = old_display
    conversation[6]["content"] = f"按刚才展示的20人开始工资核算。"
    request["user_messages"] = [item["content"] for item in conversation if item["role"] == "user"]

    scope = evidence["execution_scope"]
    decision = {
        "record_id": record_id, "name": f"人员{record_index:02d}", "reason": reason,
        "month": scope["month"], "version": scope["version"],
        "attendance_sha256": scope["attendance_sha256"], "person_matches_sha256": identity_sha,
        "confirmation_message_index": 4,
        "confirmation_message_sha256": workflow_gate._text_sha256(user_text),
        "message_source_verified": False,
    }
    evidence["scope_exclusion_decisions"] = [decision]
    canonical_decisions = json.dumps([decision], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    exclusions_sha = workflow_gate._text_sha256(canonical_decisions)
    readiness_sha = report["normalized_response_sha256"]
    scope_sha = workflow_gate._scope_digest(
        scope, identity_sha, scope["payroll_person_ids"], readiness_sha, exclusions_sha,
    )
    conversation[5]["content"] = old_display
    evidence["scope_display"] = {"message_index": 5, "scope_sha256": scope_sha}
    return request


@pytest.mark.parametrize(("total", "matched", "covered"), [(33, 25, 20), (42, 39, 31)])
def test_one_execution_authorization_binds_default_covered_scope(total: int, matched: int, covered: int):
    request = _execution_request(total, covered, matched)
    result = workflow_gate.evaluate(request)
    assert result["ok"] is True
    assert result["status"] == "EXECUTION_AUTHORIZATION_ACCEPTED"
    token = result["execution_authorization"]
    assert len(token["record_ids"]) == covered
    assert len(token["payroll_person_ids"]) == covered
    assert token["message_source_verified"] is False
    assert token["is_authorization_proof"] is False
    assert token["runtime_enforced"] is False
    assert token["readiness_report_revalidated"] is True
    assert token["payroll_response_sha256_verified"] is False
    assert token["raw_payroll_response_authenticity_verified"] is False
    assert result["next_action"] == "RECHECK_COVERAGE_AND_BATCH_THEN_SUBMIT_SAME_SCOPE"


def test_user_confirmed_conflict_exclusion_keeps_identity_ambiguous_and_allows_other_covered_people():
    request = _with_confirmed_conflict_exclusion(_execution_request(33, 20, 25))

    result = workflow_gate.evaluate(request)

    assert result["ok"] is True
    assert result["execution_authorization"]["record_ids"] == [f"rec-{i:03d}" for i in range(20)]
    assert result["execution_authorization"]["scope_exclusion_decisions"][0]["record_id"] == "rec-025"
    assert request["evidence"]["identity_matching"]["people"][25]["status"] == "ambiguous"
    assert request["evidence"]["scope_exclusion_decisions"][0]["message_source_verified"] is False


def test_scope_display_accepts_punctuation_variants_but_preserves_exact_people_set():
    request = _execution_request(33, 20, 25)
    display = request["conversation_messages"][3]["content"]
    display = display.replace("工资核算范围：", "工资核算范围:")
    display = display.replace("，共20人", ", 共 20 人")
    display = display.replace("纳入：", "纳入:").replace("、", ",")
    display = display.replace("排除事项：", "排除事项:")
    request["conversation_messages"][3]["content"] = display
    result = workflow_gate.evaluate(request)
    assert result["ok"] is True

    request = _execution_request(33, 20, 25)
    request["conversation_messages"][3]["content"] = request["conversation_messages"][3]["content"].replace(
        "人员19。排除事项：", "人员19、外部人员。排除事项：",
    )
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "EXECUTION_SCOPE_DISPLAY_PEOPLE_INCOMPLETE"


def test_conflicting_identity_without_explicit_exclusion_is_blocked():
    request = _execution_request(33, 20, 25)
    request = _with_confirmed_conflict_exclusion(request)
    request["evidence"].pop("scope_exclusion_decisions")

    result = workflow_gate.evaluate(request)

    assert result["ok"] is False
    assert result["error"] == "UNRESOLVED_IDENTITY_CONFLICT"


def test_exclusion_decision_change_invalidates_already_issued_execution_authorization():
    request = _with_confirmed_conflict_exclusion(_execution_request(33, 20, 25))
    accepted = workflow_gate.evaluate(request)
    assert accepted["ok"] is True
    request["evidence"]["execution_authorization"] = accepted["execution_authorization"]
    request["evidence"]["scope_exclusion_decisions"][0]["reason"] = "改成别的理由"
    request["action"] = "ATTENDANCE_SUBMISSION"

    result = workflow_gate.evaluate(request)

    assert result["ok"] is False
    assert result["error"] in {
        "PAYROLL_EXECUTION_AUTHORIZATION_SCOPE_MISMATCH",
        "EXECUTION_SCOPE_DISPLAY_EXCLUSIONS_INCOMPLETE",
    }


@pytest.mark.parametrize("mutation", ["stale_attendance", "stale_identity", "unrelated_message", "matched_record"])
def test_scope_exclusion_decision_is_bound_to_current_user_and_identity_facts(mutation: str):
    request = _with_confirmed_conflict_exclusion(_execution_request(33, 20, 25))
    decision = request["evidence"]["scope_exclusion_decisions"][0]
    if mutation == "stale_attendance":
        decision["attendance_sha256"] = "f" * 64
    elif mutation == "stale_identity":
        decision["person_matches_sha256"] = "f" * 64
    elif mutation == "unrelated_message":
        request["conversation_messages"][4]["content"] = "我不确认排除人员25"
        request["user_messages"][2] = request["conversation_messages"][4]["content"]
        decision["confirmation_message_sha256"] = workflow_gate._text_sha256(
            request["conversation_messages"][4]["content"]
        )
    else:
        decision["record_id"] = "rec-000"

    result = workflow_gate.evaluate(request)

    assert result["ok"] is False
    assert result["error"] in {
        "SCOPE_EXCLUSION_DECISION_INVALID", "SCOPE_EXCLUSION_USER_CONFIRMATION_REQUIRED",
        "EXECUTION_SCOPE_DISPLAY_BINDING_MISMATCH",
    }


@pytest.mark.parametrize("message", [
    "确认考勤", "人员匹配完成", "历史工资覆盖检查通过", "继续处理", "查看工资表",
    "可以核算吗？", "能否开始工资核算", "不是要开始工资核算", "先别提交，开始算工资", "把全部39人都算上",
])
def test_one_shot_execution_rejects_non_authorization_or_scope_drift(message: str):
    request = _execution_request(42, 31, 39, message)
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False


@pytest.mark.parametrize("message", [
    "开始工资核算，把王某也算上。",
    "按31人核算，但不要张某。",
    "开始核算，把李某换成赵某。",
    "按刚才范围核算，另外增加两个人。",
    "先把未匹配的人员也算进去。",
    "除了王某，其他人开始核算。",
    "开始工资核算，调整人员范围。",
])
def test_one_shot_execution_rejects_natural_language_scope_changes(message: str):
    request = _execution_request(42, 31, 39, message)
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "EXECUTION_AUTHORIZATION_SCOPE_CHANGE_REQUIRES_REVIEW"


@pytest.mark.parametrize("name", ["增加", "排除", "替换", "张某"])
def test_scope_change_detection_does_not_treat_names_or_plain_mentions_as_scope_edits(name: str):
    assert workflow_gate._scope_change_intent(f"按刚才展示的31人开始工资核算，人员包括{name}。") is False


@pytest.mark.parametrize("message", [
    "我同意按刚才展示的范围开始本次工资核算。",
    "请按上面确认的范围执行工资核算。",
    "按当前已展示人员进行工资核算。",
    "确认本次范围，开始进行工资计算。",
    "按上述人员核算2026-06工资。",
])
def test_execution_authorization_accepts_clear_natural_language_variants(message: str):
    result = workflow_gate.evaluate(_execution_request(2, 2, 2, message))
    assert result["ok"] is True


@pytest.mark.parametrize("message", [
    "按刚才展示的范围开始薪资核算。",
    "按上述31人开始薪酬核算。",
])
def test_execution_authorization_accepts_salary_calculation_synonyms(message: str):
    result = workflow_gate.evaluate(_execution_request(31, 31, 31, message))
    assert result["ok"] is True


@pytest.mark.parametrize("message", [
    "可以开始薪资核算吗？",
    "暂不开始薪资核算。",
    "查看薪资表。",
    "生成工资表。",
    "开始薪资核算，把某人也算上。",
])
def test_execution_authorization_rejects_salary_synonym_non_authorization(message: str):
    result = workflow_gate.evaluate(_execution_request(31, 31, 31, message))
    assert result["ok"] is False


@pytest.mark.parametrize("message", [
    "请按刚才展示的人员开始工资核算，可以吗？",
    "我同意按刚才展示的范围开始工资核算，但先不要提交。",
    "我想问按刚才展示的范围是否开始工资核算。",
])
def test_execution_authorization_variants_still_reject_questions_and_negation(message: str):
    result = workflow_gate.evaluate(_execution_request(2, 2, 2, message))
    assert result["ok"] is False


def test_standard_scope_display_contract_remains_bound_to_exact_people_and_effects():
    request = _execution_request(2, 2, 2)
    display_index = request["evidence"]["scope_display"]["message_index"]
    display = request["conversation_messages"][display_index]["content"]
    assert "工资核算范围" in display
    assert "2026-06" in display and "2人" in display
    assert all(person["name"] in display for person in request["evidence"]["execution_scope"]["people"])
    assert "正式提交考勤" in display and "正式预检查" in display and "工资核算" in display


@pytest.mark.parametrize(("replace", "expected_error"), [
    ("工资核算范围", "EXECUTION_SCOPE_DISPLAY_MARKER_MISSING"),
    ("纳入：", "EXECUTION_SCOPE_DISPLAY_SUMMARY_MISMATCH"),
    ("排除事项：", "EXECUTION_SCOPE_DISPLAY_SUMMARY_MISMATCH"),
])
def test_scope_display_must_follow_one_canonical_contract(replace: str, expected_error: str):
    request = _execution_request(2, 2, 2)
    index = request["evidence"]["scope_display"]["message_index"]
    request["conversation_messages"][index]["content"] = request["conversation_messages"][index]["content"].replace(
        replace, "范围标题" if replace == "工资核算范围" else "名单：", 1,
    )
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == expected_error


def test_actual_readiness_report_is_revalidated_and_compared_to_request_evidence():
    request = _execution_request(42, 31, 39)
    evidence = request["evidence"]
    report_path = Path(evidence["readiness_report_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["items"][0]["status"] = "MISSING_HISTORY"
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    result = workflow_gate.evaluate(request)

    assert result["ok"] is False
    assert result["error"] == "READINESS_REPORT_INVALID"


def test_request_cannot_claim_covered_when_actual_report_says_missing():
    request = _execution_request(42, 31, 39)
    report_path = Path(request["evidence"]["readiness_report_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    item = report["items"][0]
    item.update(status="MISSING_HISTORY", source_month=None, reason_code="MISSING_HISTORY")
    summary_item = next(
        entry for entry in report["payroll_response_summary"]["items"]
        if entry["payroll_person_id"] == item["payroll_person_id"]
    )
    summary_item.update(status="MISSING_HISTORY", source_month=None, reason_code="MISSING_HISTORY")
    report["counts"]["covered"] -= 1
    report["counts"]["missing_history"] += 1
    report["normalized_response_sha256"] = payroll_readiness._canonical_sha(report["payroll_response_summary"])
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    request["evidence"]["salary_readiness"]["normalized_response_sha256"] = report["normalized_response_sha256"]
    request["evidence"]["salary_readiness"]["counts"] = report["counts"]
    request["evidence"]["salary_readiness"]["payroll_response_summary"] = report["payroll_response_summary"]

    result = workflow_gate.evaluate(request)

    assert result["ok"] is False
    assert result["error"] == "READINESS_ITEMS_REPORT_MISMATCH"


def test_request_normalized_digest_must_match_actual_report():
    request = _execution_request(42, 31, 39)
    request["evidence"]["salary_readiness"]["normalized_response_sha256"] = "f" * 64
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "READINESS_NORMALIZED_RESPONSE_MISMATCH"


@pytest.mark.parametrize("failure", ["missing", "corrupt", "unavailable", "month", "scope"])
def test_actual_readiness_report_failure_modes_block_execution(failure: str):
    request = _execution_request(33, 20, 25)
    path = Path(request["evidence"]["readiness_report_path"])
    if failure == "missing":
        path.unlink()
    elif failure == "corrupt":
        path.write_text("{broken", encoding="utf-8")
    elif failure == "unavailable":
        path.write_text(json.dumps({"status": "UNAVAILABLE"}), encoding="utf-8")
    else:
        report = json.loads(path.read_text(encoding="utf-8"))
        if failure == "month":
            report["payroll_month"] = "2026-05"
        else:
            report["selected_record_ids"] = ["rec-000"]
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")

    result = workflow_gate.evaluate(request)
    assert result["ok"] is False


@pytest.mark.parametrize("source", ["attendance", "matches"])
def test_changed_current_readiness_inputs_invalidate_report(source: str):
    request = _execution_request(42, 31, 39)
    path = Path(request["evidence"]["attendance_path" if source == "attendance" else "person_matches_path"])
    path.write_bytes(path.read_bytes() + b" ")
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False


def test_readiness_report_must_use_fixed_internal_location_and_not_symlink():
    request = _execution_request(42, 31, 39)
    evidence = request["evidence"]
    alternate = Path(TEST_ATTENDANCE_DIR.name) / "outside-readiness.json"
    alternate.write_bytes(Path(evidence["readiness_report_path"]).read_bytes())
    evidence["readiness_report_path"] = str(alternate)
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == "READINESS_REPORT_PATH_UNTRUSTED_OR_UNAVAILABLE"


def test_symlinked_readiness_report_is_rejected():
    request = _execution_request(42, 31, 39)
    path = Path(request["evidence"]["readiness_report_path"])
    real = path.with_name("real-readiness.json")
    path.replace(real)
    path.symlink_to(real.name)
    result = workflow_gate.evaluate(request)
    path.unlink()
    real.replace(path)
    assert result["ok"] is False
    assert result["error"] == "READINESS_REPORT_PATH_UNTRUSTED_OR_UNAVAILABLE"


def test_one_execution_authorization_reuses_same_scope_through_submit_precheck_calculate():
    request = _execution_request(42, 31, 39)
    authorization = workflow_gate.evaluate(request)
    assert authorization["ok"] is True
    token = authorization["execution_authorization"]
    evidence = request["evidence"]
    evidence["execution_authorization"] = token

    submission = workflow_gate.evaluate({**request, "action": "ATTENDANCE_SUBMISSION"})
    assert submission["ok"] is True
    assert submission["submission_scope_review"]["status"] == "EXECUTION_AUTHORIZED"
    scope = evidence["execution_scope"]
    batch_id = token["batch_id"]
    evidence["submission_receipt"] = {
        "status": "SUCCEEDED", **{key: scope[key] for key in ("month", "version", "attendance_sha256", "record_ids")},
        "batch_id": batch_id, "operation_id": f"submit:{batch_id}",
    }
    evidence["payroll_operation_state"] = {
        **evidence["payroll_operation_state"],
        "operations": {
            "submission": _operation_state("SUCCEEDED", "NOT_FOUND", scope, batch_id,
                                             evidence["execution_scope"]["payroll_person_ids"])["operations"]["submission"],
            "calculation": _operation_state("SUCCEEDED", "NOT_FOUND", scope, batch_id,
                                              evidence["execution_scope"]["payroll_person_ids"])["operations"]["calculation"],
        },
    }
    precheck = workflow_gate.evaluate({**request, "action": "PAYROLL_PRECHECK"})
    assert precheck["ok"] is True
    assert precheck["next_action"] == "RUN_PRECHECK_THEN_CALCULATE_SAME_SCOPE_IF_VALID"
    evidence["payroll_precheck"] = {
        "status": "VALID", "valid": True,
        **{key: scope[key] for key in ("month", "version", "attendance_sha256", "record_ids")},
        "batch_id": batch_id, "operation_id": f"precheck:{batch_id}",
    }
    calculation = workflow_gate.evaluate({**request, "action": "PAYROLL_CALCULATION"})
    assert calculation["ok"] is True
    assert calculation["execution_authorization_reused"] is True
    assert calculation["next_action"] == "VERIFY_BATCH_RECEIPT_THEN_CALCULATE_SAME_SCOPE"


@pytest.mark.parametrize("mutation", ["attendance_sha", "identity_sha", "readiness_sha", "batch", "scope"])
def test_execution_authorization_is_invalidated_by_changed_scope_or_batch(mutation: str):
    request = _execution_request(33, 20, 25)
    token = workflow_gate.evaluate(request)["execution_authorization"]
    evidence = request["evidence"]
    evidence["execution_authorization"] = token
    if mutation == "attendance_sha":
        request["evidence"]["attendance_review"]["attendance_sha256"] = "c" * 64
        request["evidence"]["identity_matching"]["attendance_sha256"] = "c" * 64
        request["evidence"]["salary_readiness"]["attendance_sha256"] = "c" * 64
        request["evidence"]["execution_scope"]["attendance_sha256"] = "c" * 64
        request["evidence"]["batch_context"]["attendance_sha256"] = "c" * 64
    elif mutation == "identity_sha":
        request["evidence"]["identity_matching"]["person_matches_sha256"] = "d" * 64
        request["evidence"]["salary_readiness"]["person_matches_sha256"] = "d" * 64
        request["evidence"]["execution_scope"]["person_matches_sha256"] = "d" * 64
        request["evidence"]["batch_context"]["person_matches_sha256"] = "d" * 64
    elif mutation == "readiness_sha":
        request["evidence"]["salary_readiness"]["normalized_response_sha256"] = "f" * 64
    elif mutation == "batch":
        request["evidence"]["batch_context"]["batch_id"] = "task_B34-2026-06"
    else:
        request["evidence"]["execution_scope"]["payroll_person_ids"] = [999]
    result = workflow_gate.evaluate({**request, "action": "ATTENDANCE_SUBMISSION"})
    assert result["ok"] is False


def test_execution_authorization_rejects_changed_authorization_or_scope_display_message():
    request = _execution_request(33, 20, 25)
    token = workflow_gate.evaluate(request)["execution_authorization"]
    request["evidence"]["execution_authorization"] = token
    request["conversation_messages"][4]["content"] = "按刚才展示的20人开始工资核算"
    request["user_messages"][2] = request["conversation_messages"][4]["content"]
    assert workflow_gate.evaluate({**request, "action": "ATTENDANCE_SUBMISSION"})["error"] == \
        "PAYROLL_EXECUTION_AUTHORIZATION_MESSAGE_CHANGED"


def test_execution_authorization_rejects_modified_current_identity_file():
    request = _execution_request(33, 20, 25)
    token = workflow_gate.evaluate(request)["execution_authorization"]
    request["evidence"]["execution_authorization"] = token
    Path(request["evidence"]["person_matches_path"]).write_text('{"tampered":true}', encoding="utf-8")
    result = workflow_gate.evaluate({**request, "action": "ATTENDANCE_SUBMISSION"})
    assert result["ok"] is False
    assert result["error"] == "IDENTITY_MAPPING_CONTENT_MISMATCH"


def test_execution_authorization_blocks_unavailable_readiness_and_unresolved_identity():
    request = _execution_request(33, 20, 25)
    request["evidence"]["salary_readiness"]["status"] = "UNAVAILABLE"
    assert workflow_gate.evaluate(request)["ok"] is False
    request = _execution_request(33, 20, 25)
    request["evidence"]["identity_matching"]["people"][0]["status"] = "pending_confirmation"
    assert workflow_gate.evaluate(request)["ok"] is False


def test_execution_authorization_stops_on_unknown_submission_or_invalid_precheck():
    request = _execution_request(33, 20, 25)
    token = workflow_gate.evaluate(request)["execution_authorization"]
    request["evidence"]["execution_authorization"] = token
    assert workflow_gate.evaluate({**request, "action": "PAYROLL_PRECHECK"})["ok"] is False
    scope = request["evidence"]["execution_scope"]
    batch_id = token["batch_id"]
    request["evidence"]["submission_receipt"] = {
        "status": "SUCCEEDED", **{key: scope[key] for key in ("month", "version", "attendance_sha256", "record_ids")},
        "batch_id": batch_id, "operation_id": f"submit:{batch_id}",
    }
    request["evidence"]["payroll_precheck"] = {
        "status": "INVALID", "valid": False,
        **{key: scope[key] for key in ("month", "version", "attendance_sha256", "record_ids")},
        "batch_id": batch_id, "operation_id": f"precheck:{batch_id}",
    }
    assert workflow_gate.evaluate({**request, "action": "PAYROLL_CALCULATION"})["ok"] is False


def test_execution_authorization_reaches_export_only_after_successful_same_scope_calculation():
    request = _execution_request(33, 20, 25)
    token = workflow_gate.evaluate(request)["execution_authorization"]
    evidence = request["evidence"]
    evidence["execution_authorization"] = token
    scope = evidence["execution_scope"]
    batch_id = token["batch_id"]
    scope_fields = {key: scope[key] for key in ("month", "version", "attendance_sha256", "record_ids")}
    evidence["submission_receipt"] = {
        "status": "SUCCEEDED", **scope_fields, "batch_id": batch_id,
        "operation_id": f"submit:{batch_id}",
    }
    evidence["payroll_precheck"] = {
        "status": "VALID", "valid": True, **scope_fields, "batch_id": batch_id,
        "operation_id": f"precheck:{batch_id}",
    }
    evidence["calculation_receipt"] = {
        "status": "SUCCEEDED", **scope_fields, "batch_id": batch_id,
        "operation_id": f"calculate:{batch_id}",
    }
    evidence["payroll_operation_state"] = {
        **evidence["payroll_operation_state"],
        "operations": _operation_state("SUCCEEDED", "SUCCEEDED", scope, batch_id,
                                         evidence["execution_scope"]["payroll_person_ids"])["operations"],
    }
    evidence["submission_scope_review"] = {
        "status": "EXECUTION_AUTHORIZED", **scope_fields,
    }
    result = workflow_gate.evaluate({**request, "action": "PAYROLL_EXPORT"})
    assert result["ok"] is True
    assert result["next_action"] == "GENERATE_AND_DECLARE_REAL_PAYROLL_OUTPUT"

    wrong_version = workflow_gate.evaluate(_request(
        "ATTENDANCE_SUBMISSION", "我授权正式提交考勤2026-06版本review-v4的安娜和李明。",
        "本次处理范围为2026-06版本review-v5的安娜和李明。",
    ))
    assert wrong_version["ok"] is False


def test_user_scope_approval_admits_only_scope_recheck_then_stops():
    request = _request(
        "SUBMISSION_SCOPE_REVIEW",
        "本次处理范围为2026-06版本review-v5的安娜和李明。",
    )
    request["proposed_scope"] = {**SCOPE, "people": PEOPLE}
    result = workflow_gate.evaluate(request)
    assert result["ok"] is True
    assert result["next_action"] == "RECHECK_COVERAGE_FOR_EXACT_SCOPE_THEN_STOP"

    submission = _request(
        "ATTENDANCE_SUBMISSION",
        "我认可本次处理范围2026-06版本review-v5的安娜和李明，并授权正式提交考勤。",
    )
    blocked = workflow_gate.evaluate(submission)
    assert blocked["ok"] is False
    assert blocked["error"] == "PRIOR_EXACT_SCOPE_CONFIRMATION_REQUIRED"


def _scope_review_request(proposed_scope=None):
    scope = proposed_scope or {**SCOPE, "people": PEOPLE}
    labels = "安娜和李明" if len(scope["record_ids"]) == 2 else "安娜"
    request = _request(
        "SUBMISSION_SCOPE_REVIEW",
        f"本次处理范围为2026-06版本review-v5的{labels}。",
    )
    request["proposed_scope"] = scope
    return request


def test_submission_scope_review_requires_same_month_version_and_digest_as_current_review():
    assert workflow_gate.evaluate(_scope_review_request())["ok"] is True

    wrong_digest = _scope_review_request()
    wrong_digest["proposed_scope"]["attendance_sha256"] = "b" * 64
    assert workflow_gate.evaluate(wrong_digest)["error"] == "PROPOSED_SCOPE_VERSION_MISMATCH"

    wrong_month = _scope_review_request()
    wrong_month["proposed_scope"]["month"] = "2026-07"
    assert workflow_gate.evaluate(wrong_month)["error"] == "PROPOSED_SCOPE_VERSION_MISMATCH"

    wrong_version = _scope_review_request()
    wrong_version["proposed_scope"]["version"] = "review-v4"
    assert workflow_gate.evaluate(wrong_version)["error"] == "PROPOSED_SCOPE_VERSION_MISMATCH"


@pytest.mark.parametrize(
    ("evidence_key", "expected_error"),
    [
        ("identity_matching", "IDENTITY_REVIEW_SCOPE_MISMATCH"),
        ("salary_readiness", "READINESS_REVIEW_SCOPE_MISMATCH"),
    ],
)
def test_submission_scope_review_requires_identity_and_readiness_bound_to_review(evidence_key, expected_error):
    request = _scope_review_request()
    request["evidence"][evidence_key]["attendance_sha256"] = "c" * 64
    assert workflow_gate.evaluate(request)["error"] == expected_error


def test_user_approved_subset_keeps_current_review_digest_and_enters_exact_scope_recheck():
    proposed = {
        "month": SCOPE["month"], "version": SCOPE["version"],
        "attendance_sha256": SCOPE["attendance_sha256"], "record_ids": ["rec-1"],
        "people": [PEOPLE[0]],
    }
    result = workflow_gate.evaluate(_scope_review_request(proposed))
    assert result["ok"] is True
    assert result["next_action"] == "RECHECK_COVERAGE_FOR_EXACT_SCOPE_THEN_STOP"
    assert result["scope_confirmation_evidence"]["record_ids"] == ["rec-1"]
    assert result["scope_confirmation_evidence"]["attendance_sha256"] == SCOPE["attendance_sha256"]


def test_current_attendance_file_change_blocks_scope_review(tmp_path: Path):
    changed = tmp_path / "attendance.json"
    changed.write_bytes(b'{"synthetic":"attendance-corrected"}\n')
    request = _scope_review_request()
    request["evidence"]["attendance_path"] = str(changed)
    assert workflow_gate.evaluate(request)["error"] == "ATTENDANCE_REVIEW_CONTENT_MISMATCH"


def test_one_user_message_cannot_authorize_submission_and_calculation():
    both = _auth_text("授权正式提交考勤并开始工资核算")
    submission = workflow_gate.evaluate(_request("ATTENDANCE_SUBMISSION", both))
    calculation = workflow_gate.evaluate(_request("PAYROLL_CALCULATION", both))
    assert submission["ok"] is False
    assert submission["error"] == "SEPARATE_WRITE_AUTHORIZATION_REQUIRED"
    assert calculation["ok"] is False
    assert calculation["error"] == "SEPARATE_WRITE_AUTHORIZATION_REQUIRED"


def test_start_payroll_calculation_does_not_authorize_submission():
    calc_message = _auth_text("开始工资核算")
    submission = workflow_gate.evaluate(_request("ATTENDANCE_SUBMISSION", calc_message))
    calculation = workflow_gate.evaluate(_request("PAYROLL_CALCULATION", calc_message))
    assert submission["ok"] is False
    assert calculation["ok"] is True


@pytest.mark.parametrize(
    ("change", "expected_error"),
    [
        (lambda e: e.pop("batch_context"), "BATCH_CONFLICT_OR_UNVERIFIED"),
        (lambda e: e["batch_context"].update(status="CONFLICT"), "BATCH_CONFLICT_OR_UNVERIFIED"),
        (lambda e: e["batch_context"].update(batch_id="task_other-2026-06"), "BATCH_OR_OPERATION_ID_MISMATCH"),
        (lambda e: e["salary_readiness"].update(record_ids=["rec-1"]), "FINAL_SCOPE_COVERAGE_CHECK_REQUIRED"),
    ],
)
def test_batch_scope_or_readiness_failure_blocks_submission(change, expected_error: str):
    request = _request(
        "ATTENDANCE_SUBMISSION", _auth_text("授权正式提交考勤"),
        "本次处理范围为2026-06版本review-v5的安娜和李明。",
    )
    change(request["evidence"])
    result = workflow_gate.evaluate(request)
    assert result["ok"] is False
    assert result["error"] == expected_error


def test_unavailable_readiness_and_missing_user_evidence_fail_closed():
    request = _request("ATTENDANCE_SUBMISSION", _auth_text("授权正式提交考勤"))
    request["evidence"]["salary_readiness"]["status"] = "UNAVAILABLE"
    assert workflow_gate.evaluate(request)["ok"] is False
    request["user_messages"] = []
    blocked = workflow_gate.evaluate(request)
    assert blocked["ok"] is False
    assert blocked["message_source_verified"] is False


def test_valid_precheck_still_requires_separate_calculation_authorization():
    result = workflow_gate.evaluate(_request("PAYROLL_CALCULATION", "预检查通过"))
    assert result["ok"] is False
    assert result["error"] == "SEPARATE_PAYROLL_CALCULATION_AUTHORIZATION_REQUIRED"
    assert workflow_gate.evaluate(
        _request("PAYROLL_CALCULATION", "我不同意开始工资核算。")
    )["ok"] is False
    assert workflow_gate.evaluate(
        _request("PAYROLL_CALCULATION", "是否开始工资核算2026-06版本review-v5的安娜和李明？")
    )["ok"] is False

    request = _request("PAYROLL_CALCULATION", _auth_text("开始工资核算"))
    request["evidence"]["payroll_precheck"]["operation_id"] = "precheck:other"
    assert workflow_gate.evaluate(request)["error"] == "PRECHECK_BATCH_OR_OPERATION_ID_MISMATCH"


def test_precheck_requires_successful_submission_and_matching_batch_operation():
    request = _request("PAYROLL_PRECHECK", "确认考勤")
    request["evidence"]["submission_receipt"]["status"] = "PENDING"
    assert workflow_gate.evaluate(request)["ok"] is False

    request = _request("PAYROLL_PRECHECK", "确认考勤")
    request["evidence"]["submission_receipt"]["operation_id"] = "submit:other"
    assert workflow_gate.evaluate(request)["ok"] is False


def test_payroll_export_requires_matching_successful_calculation_receipt():
    result = workflow_gate.evaluate(_request("PAYROLL_EXPORT", "核算文件交付"))
    assert result["ok"] is True
    request = _request("PAYROLL_EXPORT", "核算文件交付")
    request["evidence"]["calculation_receipt"]["operation_id"] = "calculate:other"
    assert workflow_gate.evaluate(request)["ok"] is False


def test_cli_emits_structured_failure_for_missing_user_message(tmp_path: Path, capsys):
    request_path = tmp_path / "gate.json"
    request_path.write_text(json.dumps({"action": "ATTENDANCE_SUBMISSION", "user_messages": []}), encoding="utf-8")
    assert workflow_gate.main(["--request", str(request_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "WORKFLOW_BLOCKED"
    assert output["runtime_enforced"] is False
