import json
import sys
from pathlib import Path

import fitz
import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from attendance_diagnostics import diagnose
from attendance_store import save_page
from pdf_prepare import MAX_VIEWS_PER_PAGE, prepare


def _dense_attendance_pdf(path, rows=22):
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    left, right = 28, 814
    top, header_end, bottom = 38, 98, 548
    row_height = (bottom - header_end) / rows
    name_left, job_left, day_left = 58, 145, 205
    day_width = 17
    summary_left = day_left + 30 * day_width
    edges = [left, name_left, job_left, day_left]
    edges.extend(day_left + day_width * day for day in range(1, 31))
    edges.extend([summary_left, right])
    for edge in edges:
        page.draw_line((edge, top), (edge, bottom), color=(0, 0, 0), width=0.35)
    for line in range(rows + 2):
        y = top if line == 0 else header_end + (line - 1) * row_height
        if line == rows + 1:
            y = bottom
        page.draw_line((left, y), (right, y), color=(0, 0, 0), width=0.35)
    page.insert_text((32, 83), "序号", fontsize=7)
    page.insert_text((73, 83), "姓名", fontsize=7)
    page.insert_text((160, 83), "岗位", fontsize=7)
    for day in range(30):
        page.insert_text((day_left + day * day_width + 4, 83), str(day + 1), fontsize=5)
    page.insert_text((summary_left + 4, 83), "出勤", fontsize=7)
    row_centers = []
    for index in range(rows):
        y0 = header_end + index * row_height
        baseline = y0 + row_height * 0.7
        row_centers.append(round(baseline - row_height * 0.2, 4))
        page.insert_text((34, baseline), str(index + 1), fontsize=7)
        page.insert_text((66, baseline), "同名", fontsize=7)
        page.insert_text((151, baseline), "施工员", fontsize=7)
        for day in range(30):
            mark = "8" if day % 7 else "休"
            page.insert_text((day_left + day * day_width + 5, baseline), mark, fontsize=5)
        page.insert_text((summary_left + 8, baseline), "25", fontsize=7)
    doc.save(path)
    doc.close()
    return row_centers


def _person(row_index, *, same_name="同名", missing_day=None, printed="20", unresolved=False):
    daily = [
        {"day": day, "raw_mark": "8" if day <= 20 else "休", "status": "work" if day <= 20 else "rest"}
        for day in range(1, 31) if day != missing_day
    ]
    person = {
        "row_index": row_index,
        "source_view_id": "doc-1-p001-rows-01" if row_index is not None else None,
        "row_binding_status": "VERIFIED" if row_index is not None else None,
        "printed_work_days_row_index": row_index,
        "name": same_name,
        "position": "施工员",
        "printed_work_days": printed,
        "daily": daily,
    }
    if unresolved:
        person.update({"row_index": None, "row_binding_status": "UNRESOLVED", "printed_work_days_row_index": None,
                       "row_binding_warning": "姓名行边界模糊"})
    return person


def _page_result(people, *, page=1):
    return {
        "schema_version": 1,
        "document_id": "doc-1",
        "page": page,
        "month": "2026-06",
        "project": "项目A",
        "people": people,
        "warnings": [],
        "quality_warnings": [],
    }


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_fixed_views_are_deterministic_bounded_and_cover_each_row_once(tmp_path):
    pdf = tmp_path / "dense.pdf"
    row_centers = _dense_attendance_pdf(pdf)
    first = prepare([pdf], tmp_path / "first")
    second = prepare([pdf], tmp_path / "second")
    first_page = first["documents"][0]["pages"][0]
    second_page = second["documents"][0]["pages"][0]
    first_views, second_views = first_page["views"], second_page["views"]

    assert len(first_views) <= MAX_VIEWS_PER_PAGE == 4
    assert [view["view_id"] for view in first_views] == [view["view_id"] for view in second_views]
    assert [view["region"] for view in first_views] == [view["region"] for view in second_views]
    assert [view["image_sha256"] for view in first_views] == [view["image_sha256"] for view in second_views]
    assert first_views[0]["view_type"] == "overview"
    assert first_views[0]["recognition_role"] == "layout_only_no_business_fact_extraction"
    partitions = [view for view in first_views if view["view_type"] == "row_partition"]
    assert 1 <= len(partitions) <= 3
    assert all(view["source_sha256"] == first_page["source_sha256"] for view in first_views)
    assert all(view["expected_row_range"] is None for view in partitions)
    assert all(Path(view["image"]).is_file() for view in first_views)

    cores = [view["core_region"] for view in partitions]
    assert all(left["y1"] == right["y0"] for left, right in zip(cores, cores[1:]))
    scale = first_page["detail_height"] / 595
    assert cores[0]["y0"] <= row_centers[0] * scale
    assert cores[-1]["y1"] >= row_centers[-1] * scale
    for row_center in row_centers:
        pixel_y = row_center * scale
        assert sum(core["y0"] <= pixel_y < core["y1"] for core in cores) == 1
    assert all(view["region"]["y0"] <= view["core_region"]["y0"] for view in partitions)
    assert all(view["region"]["y1"] >= view["core_region"]["y1"] for view in partitions)

    manifest_before = Path(first["manifest"]).read_bytes()
    cached = prepare([pdf], tmp_path / "first")
    assert cached["cached"] is True
    assert cached["rendered_view_images"] == 0
    assert Path(first["manifest"]).read_bytes() == manifest_before


def test_same_name_different_row_indices_are_preserved_and_duplicate_index_is_rejected(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepare([pdf], workdir)
    source = tmp_path / "page.json"
    _write_json(source, _page_result([_person(41), _person(42)]))

    saved = save_page(workdir, source)
    saved_data = json.loads(Path(saved["saved"]).read_text(encoding="utf-8"))
    assert [person["name"] for person in saved_data["people"]] == ["同名", "同名"]
    assert [person["row_index"] for person in saved_data["people"]] == [41, 42]

    duplicate_workdir = tmp_path / "duplicate"
    prepare([pdf], duplicate_workdir)
    _write_json(source, _page_result([_person(41), _person(41, same_name="另一人")]))
    with pytest.raises(ValueError, match="row_index 重复"):
        save_page(duplicate_workdir, source)
    assert not Path(duplicate_workdir / ".attendance-pages/doc-1/page-1.json").exists()


def test_row_binding_must_reference_a_data_partition_not_overview(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepared = prepare([pdf], workdir)
    overview_id = prepared["documents"][0]["pages"][0]["views"][0]["view_id"]
    page_file = tmp_path / "page.json"
    person = _person(1)
    person["source_view_id"] = overview_id
    _write_json(page_file, _page_result([person]))
    with pytest.raises(ValueError, match="source_view_id"):
        save_page(workdir, page_file)


def test_printed_summary_and_note_row_indices_must_match_person_row(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepare([pdf], workdir)
    page_file = tmp_path / "page.json"
    person = _person(1)
    person["printed_work_days_row_index"] = 2
    _write_json(page_file, _page_result([person]))
    with pytest.raises(ValueError, match="印刷出勤必须明确绑定"):
        save_page(workdir, page_file)

    person["printed_work_days_row_index"] = 1
    person["note"] = "离职"
    person["note_row_index"] = 2
    _write_json(page_file, _page_result([person]))
    with pytest.raises(ValueError, match="备注必须明确绑定"):
        save_page(workdir, page_file)


def test_missing_days_require_explicit_declaration_and_printed_mismatch_is_preserved(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepare([pdf], workdir)
    source = tmp_path / "page.json"
    person = _person(1, missing_day=30, printed="25")
    _write_json(source, _page_result([person]))
    with pytest.raises(ValueError, match="missing_days"):
        save_page(workdir, source)

    person["missing_days"] = [30]
    _write_json(source, _page_result([person]))
    saved = save_page(workdir, source)
    saved_person = json.loads(Path(saved["saved"]).read_text(encoding="utf-8"))["people"][0]
    assert saved_person["printed_work_days"] == "25"
    assert sum(item["status"] == "work" for item in saved_person["daily"]) == 20
    assert saved_person["missing_days"] == [30]
    assert any("印刷实际出勤25" in warning for warning in json.loads(Path(saved["saved"]).read_text(encoding="utf-8"))["quality_warnings"])


def test_diagnostics_reports_views_rows_binding_and_printed_daily_mismatch(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepared = prepare([pdf], workdir)
    page_file = tmp_path / "page.json"
    _write_json(page_file, _page_result([_person(21, printed="25"), _person(None, unresolved=True)]))
    saved = save_page(workdir, page_file)
    attendance = {
        "schema_version": 1,
        "month": "2026-06",
        "people": [
            {**person, "record_id": f"doc-1-p1-r{index}", "project": "项目A"}
            for index, person in enumerate(json.loads(Path(saved["saved"]).read_text(encoding="utf-8"))["people"], 1)
        ],
        "source_warnings": [],
    }
    _write_json(workdir / "attendance.json", attendance)

    result = diagnose(workdir)
    assert result["view_count"] == len(prepared["documents"][0]["pages"][0]["views"])
    assert result["overview_view_count"] == 1
    assert result["row_partition_view_count"] == result["view_count"] - 1
    assert result["page_view_details"][0]["expected_row_ranges"]
    assert all(item["range"] is None for item in result["page_view_details"][0]["expected_row_ranges"])
    assert result["duplicate_row_index_count"] == 0
    assert result["missing_row_index_count"] == 1
    assert result["row_binding_anomaly_count"] >= 1
    assert result["printed_daily_mismatch_count"] >= 1
    assert result["timing"]["preprocess_rendered_view_images"] == result["row_partition_view_count"]


def test_diagnostics_counts_duplicate_row_indices_in_invalid_page(tmp_path):
    pdf = tmp_path / "dense.pdf"
    _dense_attendance_pdf(pdf, rows=4)
    workdir = tmp_path / "work"
    prepared = prepare([pdf], workdir)
    result_path = Path(prepared["documents"][0]["pages"][0]["result"])
    _write_json(result_path, _page_result([_person(7), _person(7, same_name="另一人")]))

    result = diagnose(workdir)

    assert result["duplicate_row_index_count"] == 1
    assert result["invalid_page_count"] == 1
    assert "row_index 重复" in result["invalid_pages"][0]["error"]


def test_skill_routes_overview_and_partition_roles_without_runtime_guarantee():
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    recognition = (SKILL_DIR / "references/recognition.md").read_text(encoding="utf-8")
    assert "core_region" in skill and "不从概览录入" in skill
    assert "最多四张" in recognition and "primary_rows_by_printed_row_index" in recognition
    assert "Runtime 未强制视图读取次数" in recognition
