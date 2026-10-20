from __future__ import annotations

import copy
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_payroll_workbook as exporter  # noqa: E402


COMPONENTS = exporter.COMPONENTS
MONTH = "2026-06"
BATCH = "task_A12-2026-06"


def _fixture(count: int = 31) -> dict:
    snapshot_records = []
    calc_items = []
    review_people = []
    for i in range(1, count + 1):
        name = f"合成人员{i:02d}"
        record_id = f"record-{i:02d}"
        review_people.append({"record_id": record_id, "name": name})
        snapshot_records.append({
            "record_id": record_id, "payroll_person_id": i, "roster_id": i + 100, "name_snapshot": name,
            "employee_type_snapshot": 1, "company_snapshot": "合成公司",
            "project_snapshot": "合成项目", "source_project_snapshot": "合成项目",
            "position_snapshot": "合成岗位", "source_actual_work_days": 20,
            "derived_actual_work_days": 20, "confirmed_actual_work_days": 20,
            "personal_leave_days": 0, "sick_leave_days": 0, "absent_days": 0,
            "reconciliation_status": 1, "remark": None, "items": [
                {"day": day, "status": 1 if day <= 20 else 5, "value": None,
                 "raw_value": "8" if day <= 20 else "休"}
                for day in range(1, 31)
            ],
        })
        components = [{"code": code, "name": label, "source_present": True,
                       "source_amount": "0.00" if index == 0 else "11.25",
                       "calculated_amount": "0.00" if index == 0 else "11.25"}
                      for index, (code, label) in enumerate(COMPONENTS)]
        calc_items.append({
            "batch_id": BATCH, "payroll_person_id": i, "roster_id": i + 100,
            "name": name, "employee_type": 1, "project_name": "合成项目", "company_name": "合成公司", "position": "合成岗位",
            "attendance_source": "BATCH_SNAPSHOT", "attendance_batch_operation_id": f"submit:{BATCH}",
            "his_salary_record_id": i + 200, "historical_source_month": MONTH, "components": components,
            "historical_gross_amount": "90.00", "calculated_gross_amount": "90.00", "difference": "0.00",
        })
    source_people = []
    for i in range(1, count + 1):
        source_people.append({
            "record_id": f"record-{i:02d}", "name": f"合成人员{i:02d}", "project": "合成项目",
            "company_name": "合成公司", "employee_type": 1, "position": "合成岗位", "printed_work_days": 20,
            "row_binding_status": "VERIFIED", "row_index": i, "printed_work_days_row_index": i,
            "daily": [{"day": day, "status": "work" if day <= 20 else "rest",
                       "raw_mark": "8" if day <= 20 else "休"} for day in range(1, 31)],
        })
    return {
        "workflow_state": {"phase": "CALCULATED_ARTIFACT_PENDING", "attendance_generation": 2,
                           "attendance_approved_generation": 2, "human_precheck_confirmed": True,
                           "precheck_confirmed_snapshot_id": "precheck-x", "precheck_snapshot_id": "precheck-x",
                           "calculation_completed": True},
        "latest_precheck": {"snapshot_id": "precheck-x", "valid": True, "batch_blocked": False,
                            "participant_count": count, "calculated_count": count, "blocked_count": 0},
        "attendance_snapshot": {"attendance_month": MONTH, "records": snapshot_records},
        "_source_people": source_people,
        "_source_matches": [
            {"record_id": f"record-{i:02d}", "status": "matched", "payroll_person_id": i, "roster_id": i + 100}
            for i in range(1, count + 1)
        ],
        "calculation_result": {"payroll_month": MONTH, "batch_id": BATCH, "operation_id": f"calculate:{BATCH}",
                               "precheck_snapshot_id": "precheck-x", "valid": True, "batch_blocked": False,
                               "calculation_stage": "COMPLETED", "population_count": count,
                               "participant_count": count, "calculated_count": count, "blocked_count": 0,
                               "status": "SUCCESS", "issues": [], "items": calc_items,
                               "summary": {"calculated_count": count, "population_count": count,
                                           "calculated_gross_total": str(90 * count),
                                           "historical_gross_total": str(90 * count), "difference_total": "0.00"}},
    }


def _write_inputs(tmp_path: Path, data: dict) -> tuple[Path, Path, Path]:
    input_path = tmp_path / "payroll-workbook-input.json"
    persisted_data = {key: value for key, value in data.items() if not key.startswith("_")}
    input_path.write_text(json.dumps(persisted_data, ensure_ascii=False), encoding="utf-8")
    attendance_path = tmp_path / "attendance.json"
    attendance_path.write_text(json.dumps({"schema_version": 1, "month": MONTH, "people": data["_source_people"],
                                           "source_warnings": []}, ensure_ascii=False), encoding="utf-8")
    digest = hashlib.sha256(attendance_path.read_bytes()).hexdigest()
    count = data["calculation_result"]["calculated_count"]
    record_ids = sorted(f"record-{i:02d}" for i in range(1, count + 1))
    people = [{"record_id": record_id, "payroll_person_id": int(record_id.split('-')[1]),
               "roster_id": int(record_id.split('-')[1]) + 100,
               "name": f"合成人员{int(record_id.split('-')[1]):02d}"}
              for record_id in record_ids]
    scope = {"month": MONTH, "version": "review-v2", "attendance_sha256": digest, "record_ids": record_ids}
    gate_request = {
        "action": "PAYROLL_EXPORT", "user_messages": ["工资核算文件交付"],
        "expected_submit_operation_id": f"submit:{BATCH}",
        "expected_calculate_operation_id": f"calculate:{BATCH}",
        "evidence": {
            "attendance_path": str(attendance_path),
            "attendance_review": {"status": "DECLARED", **scope, "people": people,
                                  "visible_after_user_message_index": 0},
            "identity_matching": {"status": "COMPLETE", **scope, "people": people},
            "salary_readiness": {"status": "COVERAGE_CHECKED", **scope, "people": people},
            "submission_scope_review": {"status": "CONFIRMED", **scope, "people": people,
                                        "confirmation_message_index": 0},
            "batch_context": {"status": "VERIFIED_NO_CONFLICT", "task_id": "task_A12", "batch_id": BATCH,
                              "operation_id": f"submit:{BATCH}", **scope},
            "submission_receipt": {"status": "SUCCEEDED", **scope, "batch_id": BATCH,
                                   "operation_id": f"submit:{BATCH}", "payload_sha256": "a" * 64,
                                   "payroll_person_ids": list(range(1, count + 1))},
            "payroll_precheck": {"status": "VALID", "valid": True, **scope, "people": people,
                                 "batch_id": BATCH, "operation_id": f"precheck:{BATCH}"},
            "calculation_receipt": {"status": "SUCCEEDED", **scope, "people": people, "batch_id": BATCH,
                                    "operation_id": f"calculate:{BATCH}"},
        },
    }
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps(gate_request, ensure_ascii=False), encoding="utf-8")
    calculation_response_path = tmp_path / "calculation-response.json"
    calculation_response_path.write_text(json.dumps(persisted_data["calculation_result"], ensure_ascii=False), encoding="utf-8")
    matches_path = tmp_path / "person-matches.json"
    matches_path.write_text(json.dumps({"schema_version": 1, "matching_rules_version": "W03.3",
                                        "attendance_sha256": digest,
                                        "project_aliases_sha256": exporter.person_matches._project_aliases()[1],
                                        "matches": data["_source_matches"]},
                                       ensure_ascii=False), encoding="utf-8")
    selected = set(range(1, count + 1))
    submission_records = [
        {key: record.get(key) for key in exporter.SUBMISSION_RECORD_KEYS}
        for record in persisted_data["attendance_snapshot"]["records"]
        if record.get("payroll_person_id") in selected
    ]
    submission_path = tmp_path / "submission-request.json"
    submission_path.write_text(json.dumps({"attendance_month": MONTH, "submission_mode": "BATCH_SNAPSHOT",
                                           "batch_id": BATCH, "operation_id": f"submit:{BATCH}",
                                           "records": submission_records}, ensure_ascii=False), encoding="utf-8")
    return input_path, gate_path, attendance_path


def _call_export(input_path: Path, gate_path: Path, output: Path) -> dict:
    root = input_path.parent
    return exporter.export(input_path, gate_path, output, root / "calculation-response.json",
                           root / "person-matches.json", root / "submission-request.json")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict, **kwargs) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, **kwargs), encoding="utf-8")


def _export(tmp_path: Path, data: dict | None = None, name: str = "out.xlsx") -> Path:
    input_path, gate_path, _ = _write_inputs(tmp_path, data or _fixture())
    output = tmp_path / name
    result = _call_export(input_path, gate_path, output)
    assert result["ok"] is True
    return output


def test_success_has_fixed_five_sheets_and_historical_headers(tmp_path: Path):
    path = _export(tmp_path)
    wb = load_workbook(path, data_only=False)
    assert wb.sheetnames == list(exporter.SHEETS)
    assert [wb[name].max_column for name in wb.sheetnames] == [19, 25, 17, 8, 4]
    assert [list(next(wb[name].iter_rows(min_row=3, max_row=3, values_only=True))) for name in wb.sheetnames] == [
        ["姓名", "项目", "公司/部门", "岗位", "人员类别", "基础工资", "绩效工资", "工龄工资", "职称工资", "施工补贴",
         "话费补贴", "降温费", "交通补贴", "双休日加班工资", "历史工资来源月份", "历史应发工资", "核算应发工资", "与历史差额", "状态"],
        ["姓名", "项目", "公司/部门", "岗位", "人员类别", "历史工资来源月份", "历史应发工资", "基础工资", "基础工资来源状态",
         "绩效工资", "绩效工资来源状态", "工龄工资", "工龄工资来源状态", "职称工资", "职称工资来源状态", "施工补贴",
         "施工补贴来源状态", "话费补贴", "话费补贴来源状态", "降温费", "降温费来源状态", "交通补贴", "交通补贴来源状态",
         "双休日加班工资", "双休日加班工资来源状态"],
        ["姓名", "项目", "公司/部门", "岗位", "人员类别", "来源出勤天数", "派生出勤天数", "确认出勤天数", "事假天数",
         "病假天数", "旷工天数", "对账状态", "备注", "日期", "日状态", "确认值", "原始标记"],
        ["姓名", "项目", "公司/部门", "岗位", "历史工资来源月份", "历史应发工资", "本次核算应发", "与历史差额"],
        ["姓名", "处理状态", "问题类型", "问题说明"],
    ]
    assert [wb[name].freeze_panes for name in wb.sheetnames] == ["A4"] * 5
    assert all(wb[name].auto_filter.ref.startswith("A3:") for name in wb.sheetnames)
    assert not any(c.data_type == "f" for ws in wb.worksheets for row in ws.iter_rows() for c in row)
    wb.close()


def test_31_person_result_fields_and_complete_daily_rows(tmp_path: Path):
    wb = load_workbook(_export(tmp_path), data_only=True)
    detail = wb["工资核算明细"]
    assert detail.max_row == 34
    assert detail.cell(4, 6).value == 0
    assert detail.cell(4, 17).value == 90
    assert detail.cell(4, 18).value == 0
    assert wb["考勤汇总"].max_row == 3 + 31 * 30
    assert wb["人工复核事项"].cell(4, 3).value == "无待处理事项"
    wb.close()


def test_historical_template_style_and_money_formats_are_kept(tmp_path: Path):
    wb = load_workbook(_export(tmp_path), data_only=False)
    detail = wb["工资核算明细"]
    assert detail.column_dimensions["F"].width == 18
    assert detail["A1"].font.name == "Arial" and detail["A1"].font.sz == 15
    assert detail["A1"].fill.fgColor.rgb.endswith("D9EAF7")
    assert detail["F4"].number_format == exporter.MONEY_FMT
    assert wb["考勤汇总"]["O4"].value == "出勤"
    wb.close()


def test_zero_source_and_missing_source_are_distinct(tmp_path: Path):
    data = _fixture(1)
    comps = data["calculation_result"]["items"][0]["components"]
    comps[0]["source_amount"] = "0.00"
    comps[1].update(source_present=False, source_amount=None)
    wb_path = _export(tmp_path, data)
    wb = load_workbook(wb_path, data_only=True)
    row = wb["工资基准"]
    assert row.cell(4, 8).value == 0 and row.cell(4, 9).value == "是"
    assert row.cell(4, 10).value is None and row.cell(4, 11).value == "否"
    assert row.cell(4, 12).value == 11.25 and row.cell(4, 13).value == "是"
    wb.close()


def test_missing_historical_wage_in_local_result_without_raw_dto_is_blocked(tmp_path: Path):
    data = _fixture(1)
    item = data["calculation_result"]["items"][0]
    item.update(his_salary_record_id=None, historical_source_month=None,
                historical_gross_amount=None, difference=None)
    data["calculation_result"]["summary"].update(historical_gross_total="0.00", difference_total="0.00")
    input_path, gate_path, _ = _write_inputs(tmp_path, data)
    output = tmp_path / "missing-history.xlsx"
    with pytest.raises(exporter.ExportError):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


def test_attendance_status_uses_payroll_adjusted_rest_label(tmp_path: Path):
    data = _fixture(1)
    data["attendance_snapshot"]["records"][0]["items"][0].update(status=6, value=None, raw_value="调")
    data["attendance_snapshot"]["records"][0].update(derived_actual_work_days=19, reconciliation_status=2)
    data["_source_people"][0]["daily"][0].update(status="comp_leave", raw_mark="调")
    data["_source_people"][0]["daily"][0]["user_confirmed_status"] = "comp_leave"
    wb = load_workbook(_export(tmp_path, data), data_only=True)
    assert wb["考勤汇总"].cell(4, 15).value == "调整休息"
    assert wb["考勤汇总"].cell(4, 17).value == "调"
    wb.close()


@pytest.mark.parametrize("mutation", [
    lambda d: d["calculation_result"].update(status="PARTIAL"),
    lambda d: d["calculation_result"].update(status="FAILED"),
    lambda d: d["calculation_result"]["items"].pop(),
    lambda d: d["calculation_result"]["items"][1].update(payroll_person_id=d["calculation_result"]["items"][0]["payroll_person_id"]),
    lambda d: d["calculation_result"]["items"][0]["components"].pop(),
    lambda d: d["calculation_result"]["items"][0]["components"].append(copy.deepcopy(d["calculation_result"]["items"][0]["components"][0])),
    lambda d: d["calculation_result"].update(payroll_month="2026-05"),
    lambda d: d["calculation_result"].update(batch_id="another"),
    lambda d: d["latest_precheck"].update(valid=False),
    lambda d: d["calculation_result"]["items"][0]["components"][0].update(calculated_amount="NaN"),
    lambda d: d["calculation_result"]["items"][0]["components"][0].update(source_present=1),
    lambda d: d["attendance_snapshot"]["records"][0]["items"][0].update(status=99),
])
def test_invalid_or_partial_inputs_fail_without_output(tmp_path: Path, mutation):
    data = _fixture(2)
    mutation(data)
    input_path, gate_path, _ = _write_inputs(tmp_path, data)
    output = tmp_path / "blocked.xlsx"
    with pytest.raises(exporter.ExportError):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


def test_gate_rejection_blocks_and_input_files_are_unchanged(tmp_path: Path):
    data = _fixture(1)
    input_path, gate_path, _ = _write_inputs(tmp_path, data)
    before = input_path.read_bytes()
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    gate["evidence"]["calculation_receipt"]["operation_id"] = "calculate:wrong"
    gate_path.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(exporter.ExportError):
        _call_export(input_path, gate_path, tmp_path / "blocked.xlsx")
    assert input_path.read_bytes() == before
    assert not (tmp_path / "blocked.xlsx").exists()


def test_non_calculated_attendance_person_is_preserved_and_flagged(tmp_path: Path):
    data = _fixture(1)
    extra = copy.deepcopy(data["attendance_snapshot"]["records"][0])
    extra["record_id"] = "record-unmatched"
    extra["payroll_person_id"] = None
    extra["roster_id"] = None
    extra["name_snapshot"] = "未匹配合成人员"
    data["attendance_snapshot"]["records"].append(extra)
    source_extra = copy.deepcopy(data["_source_people"][0])
    source_extra.update(record_id="record-unmatched", name="未匹配合成人员")
    source_extra["row_index"] = 2
    source_extra["printed_work_days_row_index"] = 2
    data["_source_people"].append(source_extra)
    data["_source_matches"].append({"record_id": "record-unmatched", "status": "unmatched",
                                    "payroll_person_id": None, "roster_id": None})
    wb = load_workbook(_export(tmp_path, data), data_only=True)
    attendance = wb["考勤汇总"]
    assert attendance.max_row == 3 + 60
    assert sum(1 for row in attendance.iter_rows(min_row=4, values_only=True) if row[0] == "未匹配合成人员") == 30
    assert any(row[0] == "未匹配合成人员" and row[2] == "未纳入核算"
               for row in wb["人工复核事项"].iter_rows(min_row=4, values_only=True))
    wb.close()


def test_repeated_export_has_same_business_cells_and_never_overwrites_input(tmp_path: Path):
    data = _fixture(2)
    input_path, gate_path, _ = _write_inputs(tmp_path, data)
    before = input_path.read_bytes()
    one = _call_export(input_path, gate_path, tmp_path / "one.xlsx")
    two = _call_export(input_path, gate_path, tmp_path / "two.xlsx")
    assert input_path.read_bytes() == before
    w1, w2 = load_workbook(one["path"], data_only=True), load_workbook(two["path"], data_only=True)
    for name in w1.sheetnames:
        assert list(w1[name].values) == list(w2[name].values)
    w1.close()
    w2.close()


def test_existing_output_is_never_overwritten(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    output = tmp_path / "already.xlsx"
    output.write_bytes(b"keep")
    with pytest.raises(exporter.ExportError, match="OUTPUT_PATH_INVALID_OR_EXISTS"):
        _call_export(input_path, gate_path, output)
    assert output.read_bytes() == b"keep"


def test_missing_or_corrupt_calculation_input_is_blocked(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    input_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(exporter.ExportError, match="INPUT_UNREADABLE"):
        _call_export(input_path, gate_path, tmp_path / "bad-json.xlsx")
    input_path.unlink()
    with pytest.raises(exporter.ExportError, match="INPUT_UNREADABLE"):
        _call_export(input_path, gate_path, tmp_path / "missing.xlsx")
    assert not (tmp_path / "bad-json.xlsx").exists()
    assert not (tmp_path / "missing.xlsx").exists()


def test_original_calculation_dto_blocks_self_consistent_tampering(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    data = _read_json(input_path)
    result = data["calculation_result"]
    item = result["items"][0]
    item["components"][0]["calculated_amount"] = "1.00"
    item["calculated_gross_amount"] = "91.00"
    item["difference"] = "1.00"
    result["summary"]["calculated_gross_total"] = "91.00"
    result["summary"]["difference_total"] = "1.00"
    _write_json(input_path, data)
    output = tmp_path / "tampered-internal.xlsx"
    with pytest.raises(exporter.ExportError, match="CALCULATION_RESULT_SOURCE_MISMATCH"):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


@pytest.mark.parametrize("mutate", [
    lambda result: (result["items"][0].update(historical_gross_amount="91.00", difference="-1.00"),
                    result["summary"].update(historical_gross_total="91.00", difference_total="-1.00")),
    lambda result: result["items"][0]["components"][0].update(source_present=False, source_amount=None),
    lambda result: result["items"].pop(),
    lambda result: result["items"][0]["components"][0].update(source_amount="999.00"),
])
def test_calculation_field_changes_are_blocked_against_raw_response(tmp_path: Path, mutate):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    data = _read_json(input_path)
    mutate(data["calculation_result"])
    _write_json(input_path, data)
    output = tmp_path / "changed-calculation.xlsx"
    with pytest.raises(exporter.ExportError, match="CALCULATION_RESULT_SOURCE_MISMATCH"):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


@pytest.mark.parametrize("mutation", [
    lambda rec: rec["items"][0].update(status=5),
    lambda rec: rec["items"][0].update(raw_value="伪造"),
    lambda rec: rec.update(confirmed_actual_work_days="19"),
    lambda rec: rec.update(payroll_person_id=999),
])
def test_attendance_snapshot_must_match_current_confirmed_source(tmp_path: Path, mutation):
    input_path, gate_path, attendance_path = _write_inputs(tmp_path, _fixture(1))
    data = _read_json(input_path)
    mutation(data["attendance_snapshot"]["records"][0])
    _write_json(input_path, data)
    output = tmp_path / "changed-attendance.xlsx"
    with pytest.raises(exporter.ExportError):
        _call_export(input_path, gate_path, output)
    assert not output.exists()
    assert attendance_path.exists()


def test_snapshot_cannot_drop_an_attendance_record(tmp_path: Path):
    data = _fixture(2)
    data["attendance_snapshot"]["records"].pop()
    input_path, gate_path, _ = _write_inputs(tmp_path, data)
    output = tmp_path / "dropped-attendance.xlsx"
    with pytest.raises(exporter.ExportError, match="ATTENDANCE_SNAPSHOT_SOURCE_SCOPE_MISMATCH"):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


def test_current_attendance_sha_must_match_review_and_identity_mapping(tmp_path: Path):
    input_path, gate_path, attendance_path = _write_inputs(tmp_path, _fixture(1))
    attendance = _read_json(attendance_path)
    attendance["people"][0]["name"] = "修改后姓名"
    _write_json(attendance_path, attendance)
    output = tmp_path / "stale-attendance.xlsx"
    with pytest.raises(exporter.ExportError, match="ATTENDANCE_REVIEW_SOURCE_MISMATCH"):
        _call_export(input_path, gate_path, output)
    assert not output.exists()


def test_canonical_json_comparison_ignores_whitespace_and_key_order(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    raw_path = tmp_path / "calculation-response.json"
    _write_json(raw_path, _read_json(raw_path), indent=4, sort_keys=True)
    result = _call_export(input_path, gate_path, tmp_path / "canonical.xlsx")
    assert result["ok"] is True


def test_raw_calculation_response_missing_corrupt_or_wrapped_is_blocked(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    raw_path = tmp_path / "calculation-response.json"
    original = raw_path.read_bytes()
    raw_path.unlink()
    with pytest.raises(exporter.ExportError, match="RAW_CALCULATION_RESPONSE_UNREADABLE"):
        _call_export(input_path, gate_path, tmp_path / "missing-response.xlsx")
    raw_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(exporter.ExportError):
        _call_export(input_path, gate_path, tmp_path / "corrupt-response.xlsx")
    _write_json(raw_path, {"result": json.loads(original)})
    with pytest.raises(exporter.ExportError, match="RAW_CALCULATION_RESPONSE_STRUCTURE_INVALID"):
        _call_export(input_path, gate_path, tmp_path / "wrapped-response.xlsx")


def test_unknown_calculation_dto_field_is_not_silently_discarded(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    raw_path = tmp_path / "calculation-response.json"
    raw = _read_json(raw_path)
    raw["unexpected_field"] = "not silently ignored"
    _write_json(raw_path, raw)
    with pytest.raises(exporter.ExportError, match="RAW_CALCULATION_RESPONSE_STRUCTURE_INVALID"):
        _call_export(input_path, gate_path, tmp_path / "unknown-field.xlsx")


def test_submission_request_must_match_snapshot_and_receipt_scope(tmp_path: Path):
    input_path, gate_path, _ = _write_inputs(tmp_path, _fixture(1))
    request_path = tmp_path / "submission-request.json"
    request = _read_json(request_path)
    request["records"][0]["items"][0]["raw_value"] = "伪造"
    _write_json(request_path, request)
    with pytest.raises(exporter.ExportError, match="SUBMISSION_REQUEST_SNAPSHOT_MISMATCH"):
        _call_export(input_path, gate_path, tmp_path / "request-mismatch.xlsx")
    assert not (tmp_path / "request-mismatch.xlsx").exists()


def test_successful_export_never_modifies_source_files(tmp_path: Path):
    input_path, gate_path, attendance_path = _write_inputs(tmp_path, _fixture(1))
    paths = [input_path, gate_path, attendance_path, tmp_path / "calculation-response.json",
             tmp_path / "person-matches.json", tmp_path / "submission-request.json"]
    before = {path: path.read_bytes() for path in paths}
    _call_export(input_path, gate_path, tmp_path / "read-only.xlsx")
    assert {path: path.read_bytes() for path in paths} == before


def test_historical_success_workbook_matches_payroll_result_without_modifying_it():
    historical = Path("/Users/ccy/.leros/projects/1/prj_Z31vkWS1d1/repo")
    input_path = historical / ".payroll-workbook-input.json"
    workbook_path = historical / "2026年6月工资核算表.xlsx"
    if not input_path.is_file() or not workbook_path.is_file():
        pytest.skip("historical read-only sample is unavailable")
    before = (input_path.stat().st_mtime_ns, workbook_path.stat().st_mtime_ns)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    book = load_workbook(workbook_path, data_only=True, read_only=True)
    ws = book["工资核算明细"]
    source = {row["name"]: row for row in data["calculation_result"]["items"]}
    code_order = [code for code, _ in COMPONENTS]
    checked = 0
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[0]:
            continue
        item = source[row[0]]
        values = {component["code"]: Decimal(component["calculated_amount"]) for component in item["components"]}
        assert [Decimal(str(value)) for value in row[5:14]] == [values[code] for code in code_order]
        assert Decimal(str(row[15])) == Decimal(item["historical_gross_amount"])
        assert Decimal(str(row[16])) == Decimal(item["calculated_gross_amount"])
        assert Decimal(str(row[17])) == Decimal(item["difference"])
        checked += 1
    book.close()
    assert checked == 31
    assert before == (input_path.stat().st_mtime_ns, workbook_path.stat().st_mtime_ns)
