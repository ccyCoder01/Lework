import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from attendance_export import export, render
from attendance_review import analyze, apply_file, apply_operations


def person(record_id="doc-1-p1-r1", name="张三", project="项目A", **extra):
    daily = [{"day": day, "raw_mark": "8", "status": "work"} for day in range(1, 26)]
    daily += [{"day": day, "raw_mark": "休", "status": "rest"} for day in range(26, 31)]
    return {"record_id": record_id, "row_index": 1, "row_binding_status": "VERIFIED",
            "printed_work_days_row_index": 1, "name": name, "position": "施工员", "printed_work_days": "25", "project": project,
            "source_document": "/source/attendance.pdf", "note": "", "daily": daily, **extra}


def dataset(*people):
    return {"schema_version": 1, "month": "2026-06", "people": list(people)}


def test_export_has_fixed_six_columns_and_no_daily_matrix(tmp_path):
    text, report = render(dataset(person()))
    assert "| 序号 | 姓名 | 岗位 | 实际出勤 | 缺勤合计 | 备注 |" in text
    assert "每日明细" not in text
    assert "1–30日" not in text and "1–15日" not in text and "16–30日" not in text
    row = next(line for line in text.splitlines() if line.startswith("| 1 |"))
    assert len(row.split("|")[1:-1]) == 6
    assert report["people_count"] == 1


def test_page_warnings_survive_into_export():
    data = dataset(person())
    data["source_warnings"] = [{"document_id": "doc-1", "page": 1, "warning": "人员行范围待核"}]
    text, _ = render(data)
    assert "人员行范围待核" in text
    assert "doc-1/page-1" in text


def test_single_daily_and_confirmed_total_updates_recalculate(tmp_path):
    data = dataset(person())
    request = {"operations": [
        {"op": "set_daily_status", "record_id": "doc-1-p1-r1", "day": 25, "status": "rest", "confirmed_mark": "用户确认休息"},
        {"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 24},
    ]}
    updated = apply_operations(data, request)
    assert updated["people"][0]["confirmed_work_days"] == 24
    assert updated["people"][0]["daily"][24]["status"] == "work"
    assert updated["people"][0]["daily"][24]["raw_mark"] == "8"
    assert updated["people"][0]["daily"][24]["user_confirmed_status"] == "rest"
    report = analyze(updated)
    assert report["stats"]["doc-1-p1-r1"]["actual_work_days"] == 24
    assert any(issue["reason"] == "印刷出勤与逐日统计不一致" for issue in report["issues"])


def test_batch_update_is_all_or_nothing(tmp_path):
    data_path = tmp_path / "attendance.json"
    request_path = tmp_path / "request.json"
    original = dataset(person(), person("doc-1-p1-r2", "李四"))
    data_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    request_path.write_text(json.dumps({"operations": [
        {"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 20},
        {"op": "set_daily_status", "record_id": "missing", "day": 1, "status": "work"},
    ]}), encoding="utf-8")
    before = data_path.read_bytes()
    with pytest.raises(ValueError, match="找不到 record_id"):
        apply_file(data_path, request_path)
    assert data_path.read_bytes() == before


def test_valid_batch_changes_multiple_people(tmp_path):
    data = dataset(person(), person("doc-1-p1-r2", "李四"))
    updated = apply_operations(data, {"operations": [
        {"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 24},
        {"op": "set_actual_work_days", "record_id": "doc-1-p1-r2", "value": 23},
    ]})
    assert [p["confirmed_work_days"] for p in updated["people"]] == [24, 23]


def test_unknown_symbol_status_and_missing_dates_are_pending():
    item = person()
    item["daily"][0] = {"day": 1, "raw_mark": "?", "status": "unknown"}
    item["daily"] = [d for d in item["daily"] if d["day"] != 2]
    report = analyze(dataset(item))
    stats = report["stats"][item["record_id"]]
    assert stats["actual_work_days"] == 25
    assert stats["absence_days"] == "待确认"
    assert any(i["reason"] == "状态待确认" for i in report["issues"])
    assert any(i["reason"] == "日期缺失" for i in report["issues"])


def test_unmapped_raw_mark_cannot_be_counted_as_work():
    item = person()
    item["daily"][0] = {"day": 1, "raw_mark": "调", "status": "work"}
    report = analyze(dataset(item))
    assert report["stats"][item["record_id"]]["actual_work_days"] == 25
    assert any(i["field"] == "2026-06-01" and i["reason"] == "状态待确认" for i in report["issues"])


def test_confirmed_absence_symbol_is_counted_without_calendar_subtraction():
    item = person()
    item["daily"][24] = {"day": 25, "raw_mark": "事", "status": "personal_leave"}
    stats = analyze(dataset(item))["stats"][item["record_id"]]
    assert stats["absence_days"] == 1
    assert stats["actual_work_days"] == 25


@pytest.mark.parametrize("status", ["transfer", "departed"])
def test_transfer_or_departure_is_not_counted_as_absence(status):
    item = person()
    item["daily"][-1] = {"day": 30, "raw_mark": "离", "status": status}
    report = analyze(dataset(item))
    assert report["stats"][item["record_id"]]["absence_days"] == "待确认"
    assert report["stats"][item["record_id"]]["actual_work_days"] == 25


def test_cross_project_duplicate_requires_two_effective_work_statuses():
    left = person(confirmed_person_id="person-7")
    right = person("doc-2-p1-r1", "张三", "项目B", confirmed_person_id="person-7")
    report = analyze(dataset(left, right))
    conflicts = [i for i in report["issues"] if "跨项目日期重复出勤" in i["reason"]]
    assert conflicts
    assert conflicts[0]["record_id"] == right["record_id"]
    assert conflicts[0]["other_record_id"] == left["record_id"]
    assert conflicts[0]["project"] == "项目B" and conflicts[0]["other_project"] == "项目A"
    assert conflicts[0]["field"] == "2026-06-01"
    text, _ = render(dataset(left, right))
    assert "doc-1-p1-r1/项目A ↔ doc-2-p1-r1/项目B 2026-06-01" in text


@pytest.mark.parametrize("raw_mark,status", [("休", "rest"), ("换", "comp_leave")])
def test_cross_project_attendance_and_rest_or_comp_leave_is_not_duplicate(raw_mark, status):
    left = person(confirmed_person_id="person-7")
    right = person("doc-2-p1-r1", "张三", "项目B", confirmed_person_id="person-7")
    right["daily"][0] = {"day": 1, "raw_mark": raw_mark, "status": status}
    report = analyze(dataset(left, right))
    assert not any(i.get("field") == "2026-06-01" and "跨项目日期重复出勤" in i["reason"] for i in report["issues"])


@pytest.mark.parametrize("raw_mark,status", [("?", "unknown"), ("调", "transfer"), ("离", "departed")])
def test_unknown_transfer_or_departed_status_is_not_duplicate(raw_mark, status):
    left = person(confirmed_person_id="person-7")
    right = person("doc-2-p1-r1", "张三", "项目B", confirmed_person_id="person-7")
    right["daily"][0] = {"day": 1, "raw_mark": raw_mark, "status": status}
    report = analyze(dataset(left, right))
    assert not any(i.get("field") == "2026-06-01" and "跨项目日期重复出勤" in i["reason"] for i in report["issues"])


def test_same_name_without_confirmed_identity_is_not_duplicate():
    same_name_a, same_name_b = person(), person("doc-2-p1-r1", "张三", "项目B")
    report = analyze(dataset(same_name_a, same_name_b))
    assert report["people_count"] == 2
    assert not any("跨项目日期重复出勤" in i["reason"] for i in report["issues"])


def test_user_confirmed_daily_status_participates_in_cross_project_check():
    left = person(confirmed_person_id="person-7")
    right = person("doc-2-p1-r1", "张三", "项目B", confirmed_person_id="person-7")
    left["daily"][0] = {"day": 1, "raw_mark": "休", "status": "rest", "user_confirmed_status": "work"}
    report = analyze(dataset(left, right))
    assert any(i.get("field") == "2026-06-01" and "跨项目日期重复出勤" in i["reason"] for i in report["issues"])


@pytest.mark.parametrize("value", ["5", True, False, -1, 31])
def test_invalid_confirmed_work_days_are_rejected(value):
    item = person(confirmed_work_days=value)
    with pytest.raises(ValueError, match="confirmed_work_days"):
        analyze(dataset(item))


@pytest.mark.parametrize("value", [1, "", "   ", " person-1", "person-1 "])
def test_invalid_confirmed_person_id_is_rejected(value):
    with pytest.raises(ValueError, match="confirmed_person_id"):
        analyze(dataset(person(confirmed_person_id=value)))


@pytest.mark.parametrize("field,value", [
    ("user_confirmed_status", "nonsense"), ("user_confirmed_status", None),
    ("user_confirmed_mark", 8), ("user_confirmed_mark", None),
])
def test_invalid_daily_confirmation_fields_are_rejected(field, value):
    item = person()
    item["daily"][0][field] = value
    with pytest.raises(ValueError, match="user_confirmed"):
        analyze(dataset(item))


@pytest.mark.parametrize("value", [0, 30])
def test_confirmed_work_days_valid_integer_boundaries(value):
    assert analyze(dataset(person(confirmed_work_days=value)))["stats"]["doc-1-p1-r1"]["actual_work_days"] == value


def test_invalid_confirmation_does_not_modify_work_file_or_export(tmp_path):
    data = dataset(person(confirmed_work_days=True))
    data_path, request_path, output_path = tmp_path / "attendance.json", tmp_path / "request.json", tmp_path / "考勤确认表.md"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    request_path.write_text(json.dumps({"operations": [{"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 20}]}), encoding="utf-8")
    before = data_path.read_bytes()
    with pytest.raises(ValueError, match="confirmed_work_days"):
        apply_file(data_path, request_path)
    assert data_path.read_bytes() == before
    with pytest.raises(ValueError, match="confirmed_work_days"):
        export(data_path, output_path)
    assert not output_path.exists()


def test_check_cli_rejects_invalid_confirmation_fields(tmp_path):
    data_path = tmp_path / "attendance.json"
    data_path.write_text(json.dumps(dataset(person(confirmed_work_days="25")), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SKILL_DIR / "scripts/attendance_review.py"), "check", "--data", str(data_path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stderr)["ok"] is False


def test_explicit_source_warning_resolution_preserves_original_and_clears_only_that_warning(tmp_path):
    data = dataset(person())
    data["source_warnings"] = [
        {"document_id": "doc-1", "page": 1, "warning": "某日标记待核"},
        {"document_id": "doc-1", "page": 2, "warning": "人员行范围待核"},
    ]
    data["people"][0]["daily"][0] = {"day": 1, "raw_mark": "?", "status": "unknown"}
    path, request_path = tmp_path / "attendance.json", tmp_path / "request.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    request_path.write_text(json.dumps({"operations": [
        {"op": "set_daily_status", "record_id": "doc-1-p1-r1", "day": 1, "status": "work", "confirmed_mark": "用户确认出勤"},
        {"op": "resolve_source_warning", "warning_index": 0, "confirm_resolved": True},
    ]}), encoding="utf-8")
    before_warnings = data["source_warnings"]
    apply_file(path, request_path)
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["source_warnings"] == before_warnings
    assert updated["resolved_source_warnings"] == [{
        "warning_index": 0, "document_id": "doc-1", "page": 1, "warning": "某日标记待核"
    }]
    report = analyze(updated)
    source_issues = [i for i in report["issues"] if "待核" in i["reason"]]
    assert [i["reason"] for i in source_issues] == ["人员行范围待核"]
    assert not any(i.get("field") == "2026-06-01" and i["reason"] == "状态待确认" for i in report["issues"])
    text, exported_report = render(updated)
    assert "某日标记待核" not in text and "人员行范围待核" in text
    assert report["issues"] == exported_report["issues"]


def test_modified_source_warning_cannot_be_hidden_by_stale_resolution_binding():
    data = dataset(person())
    data["source_warnings"] = [{"document_id": "doc-1", "page": 1, "warning": "原始警告"}]
    data["resolved_source_warnings"] = [{"warning_index": 0, "document_id": "doc-1", "page": 1, "warning": "原始警告"}]
    data["source_warnings"][0]["warning"] = "被篡改的警告"
    with pytest.raises(ValueError, match="绑定"):
        analyze(data)


def test_warning_resolution_requires_explicit_confirmation_and_does_not_write(tmp_path):
    data = dataset(person())
    data["source_warnings"] = [{"document_id": "doc-1", "page": 1, "warning": "结构待核"}]
    data_path, request_path = tmp_path / "attendance.json", tmp_path / "request.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    request_path.write_text(json.dumps({"operations": [{"op": "resolve_source_warning", "warning_index": 0, "confirm_resolved": False}]}), encoding="utf-8")
    before = data_path.read_bytes()
    with pytest.raises(ValueError, match="confirm_resolved"):
        apply_file(data_path, request_path)
    assert data_path.read_bytes() == before


def test_repeated_export_does_not_change_attendance_json(tmp_path):
    data_path, output_path = tmp_path / "attendance.json", tmp_path / "考勤确认表.md"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    before = data_path.read_bytes()
    first = export(data_path, output_path)
    first_text = output_path.read_text(encoding="utf-8")
    second = export(data_path, output_path)
    assert first["output"] == second["output"]
    assert output_path.read_text(encoding="utf-8") == first_text
    assert data_path.read_bytes() == before


def test_export_rejects_unrelated_output_name():
    with pytest.raises(ValueError, match="考勤确认表.md"):
        export(Path("unused.json"), Path("other.md"))


def test_export_does_not_overwrite_unrelated_file(tmp_path):
    data_path, output_path = tmp_path / "attendance.json", tmp_path / "考勤确认表.md"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    output_path.write_text("unrelated content\n", encoding="utf-8")
    before = output_path.read_bytes()
    with pytest.raises(ValueError, match="拒绝覆盖"):
        export(data_path, output_path)
    assert output_path.read_bytes() == before


def test_review_cli_returns_machine_readable_success(tmp_path):
    data_path, request_path = tmp_path / "attendance.json", tmp_path / "request.json"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    request_path.write_text(json.dumps({"operations": [
        {"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 25}
    ]}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SKILL_DIR / "scripts/attendance_review.py"), "apply", "--data", str(data_path), "--request", str(request_path)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["ok"] is True


def test_export_filesystem_failure_is_explicit(tmp_path):
    data_path = tmp_path / "attendance.json"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    with pytest.raises(OSError):
        export(data_path, blocker / "考勤确认表.md")


def test_export_cli_reports_filesystem_failure_as_json(tmp_path):
    data_path = tmp_path / "attendance.json"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SKILL_DIR / "scripts/attendance_export.py"), "--data", str(data_path), "--output", str(blocker / "考勤确认表.md")], capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(result.stderr)["ok"] is False


def test_export_cli_returns_metadata(tmp_path):
    data_path, output_path = tmp_path / "attendance.json", tmp_path / "考勤确认表.md"
    data_path.write_text(json.dumps(dataset(person()), ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(SKILL_DIR / "scripts/attendance_export.py"), "--data", str(data_path), "--output", str(output_path)], capture_output=True, text=True, check=True)
    response = json.loads(result.stdout)
    assert response["ok"] is True
    assert response["people_count"] == 1 and response["project_count"] == 1
    assert Path(response["output"]) == output_path.resolve()


def test_skill_requires_artifact_declaration_success_check():
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "artifact_declare" in skill
    assert '"mime_type": "text/markdown"' in skill
    assert '"artifact_type": "file"' in skill and '"is_final": true' in skill
    assert "ok` 为 `true`" in skill
    assert "明确表示声明尚未写入" in skill and "结果不明确时不得重复追加声明" in skill
    assert "只有观察到实际 UI 证据时才能声称卡片已显示" in skill
