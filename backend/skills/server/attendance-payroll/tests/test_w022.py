import json
import sys
from pathlib import Path

import fitz

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from attendance_diagnostics import diagnose
from attendance_export import render
from attendance_review import analyze
from attendance_store import save_page
from pdf_prepare import prepare


def _person(record_id="doc-1-p1-r1", *, missing_day=None):
    daily = []
    for day in range(1, 31):
        if day == missing_day:
            continue
        if day == 1:
            daily.append({"day": day, "raw_mark": "?", "status": "unknown"})
        elif day <= 26:
            daily.append({"day": day, "raw_mark": "8", "status": "work"})
        else:
            daily.append({"day": day, "raw_mark": "休", "status": "rest"})
    return {
        "record_id": record_id, "row_index": 1, "name": "测试人员", "position": "施工员",
        "printed_work_days": "25", "project": "项目A", "source_document": "source.pdf",
        "daily": daily,
    }


def _attendance(person):
    return {"schema_version": 1, "month": "2026-06", "people": [person], "source_warnings": []}


def _save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_prepare_manifest_matches_actual_pdf_pages_and_records_its_own_timing(tmp_path):
    pdf_path = tmp_path / "two-pages.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.new_page()
    pdf.save(pdf_path)
    pdf.close()

    workdir = tmp_path / "work"
    first = prepare([pdf_path], workdir)
    manifest = json.loads((workdir / "attendance-manifest.json").read_text(encoding="utf-8"))
    with fitz.open(pdf_path) as source:
        actual_pages = source.page_count
    assert first["total_pages"] == actual_pages == sum(len(doc["pages"]) for doc in manifest["documents"])
    assert first["rendered_page_images"] == 2 and first["reused_page_images"] == 0
    assert first["preprocess_elapsed_ms"] >= 0

    second = prepare([pdf_path], workdir)
    assert second["rendered_page_images"] == 0 and second["reused_page_images"] == 2
    runtime = json.loads((workdir / ".attendance-runtime.json").read_text(encoding="utf-8"))
    assert len(runtime["events"]) == 2
    assert runtime["events"][0]["clock"] == "time.perf_counter_ns"


def test_saved_page_cannot_be_overwritten_by_second_recognition(tmp_path):
    pdf_path = tmp_path / "one-page.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(pdf_path)
    pdf.close()
    workdir = tmp_path / "work"
    prepare([pdf_path], workdir)
    result_path = tmp_path / "result.json"
    _save_json(result_path, {
        "schema_version": 1, "document_id": "doc-1", "page": 1, "month": "2026-06",
        "project": "项目A", "people": [_person()], "warnings": [],
    })
    saved = save_page(workdir, result_path)
    before = Path(saved["saved"]).read_bytes()
    with pytest.raises(ValueError, match="不可覆盖"):
        save_page(workdir, result_path)
    assert Path(saved["saved"]).read_bytes() == before


def test_unknown_and_missing_days_remain_pending_not_work_or_rest():
    report = analyze(_attendance(_person(missing_day=30)))
    stats = report["stats"]["doc-1-p1-r1"]
    assert stats["observed_work_days"] == 25
    assert stats["actual_work_days"] == "待确认"
    assert stats["absence_days"] == "待确认"
    assert any(issue["reason"] == "状态待确认" and issue["field"] == "2026-06-01" for issue in report["issues"])
    assert any(issue["reason"] == "日期缺失" and issue["days"] == [30] for issue in report["issues"])


def test_diagnostics_reads_json_only_and_marks_unavailable_timing_null(tmp_path):
    workdir = tmp_path / "work"
    result_path = workdir / ".attendance-pages/doc-1/page-1.json"
    person = _person()
    attendance = _attendance(person)
    _save_json(workdir / "attendance-manifest.json", {
        "schema_version": 1,
        "documents": [{"document_id": "doc-1", "source": str(workdir / "unreadable.pdf"), "pages": [
            {"page": 1, "image": str(workdir / "missing-image.png"), "result": str(result_path)},
        ]}],
    })
    _save_json(result_path, {
        "schema_version": 1, "document_id": "doc-1", "page": 1, "month": "2026-06",
        "project": "项目A", "people": [person], "warnings": [],
    })
    _save_json(workdir / "attendance.json", attendance)
    manifest_before = (workdir / "attendance-manifest.json").read_bytes()
    page_before = result_path.read_bytes()
    attendance_before = (workdir / "attendance.json").read_bytes()

    result = diagnose(workdir)

    assert result["pdf_count"] == 1 and result["pdf_page_count"] == 1
    assert result["page_people_counts"] == [{"document_id": "doc-1", "page": 1, "people_count": 1}]
    assert result["page_people_record_count"] == result["attendance_record_count"] == 1
    assert result["saved_page_count"] == 1 and result["missing_page_count"] == result["invalid_page_count"] == 0
    assert result["raw_unknown_status_count"] == result["current_unknown_status_count"] == 1
    assert result["missing_daily_day_count"] == 0
    assert result["current_exception_count"] == len(analyze(attendance)["issues"])
    assert result["timing"]["preprocess_elapsed_ms"] is None
    assert result["timing"]["preprocess_timing_status"] == "unavailable"
    assert result["timing"]["model_inference_ms"] is None
    assert result["timing"]["agent_image_read_call_count"] is None
    assert (workdir / ".attendance-diagnostics.json").is_file()
    assert (workdir / "attendance-manifest.json").read_bytes() == manifest_before
    assert result_path.read_bytes() == page_before
    assert (workdir / "attendance.json").read_bytes() == attendance_before
    assert not (workdir / "unreadable.pdf").exists()


def test_diagnostics_aggregates_measured_preprocessing_events(tmp_path):
    workdir = tmp_path / "work"
    _save_json(workdir / "attendance-manifest.json", {
        "schema_version": 1,
        "documents": [{"document_id": "doc-1", "source": "not-opened.pdf", "pages": []}],
    })
    _save_json(workdir / ".attendance-runtime.json", {
        "schema_version": 1,
        "events": [
            {"stage": "pdf_prepare", "elapsed_ms": 12.5, "rendered_page_images": 2, "reused_page_images": 0},
            {"stage": "pdf_prepare", "elapsed_ms": 3.5, "rendered_page_images": 0, "reused_page_images": 2},
        ],
    })

    result = diagnose(workdir)

    assert result["timing"]["preprocess_elapsed_ms"] == 16
    assert result["timing"]["preprocess_invocation_count"] == 2
    assert result["timing"]["preprocess_rendered_page_images"] == 2
    assert result["timing"]["preprocess_reused_page_images"] == 2
    assert result["timing"]["model_inference_ms"] is None


def test_diagnostics_counts_missing_days_and_current_exceptions(tmp_path):
    workdir = tmp_path / "work"
    result_path = workdir / ".attendance-pages/doc-1/page-1.json"
    person = _person(missing_day=30)
    attendance = _attendance(person)
    _save_json(workdir / "attendance-manifest.json", {
        "schema_version": 1,
        "documents": [{"document_id": "doc-1", "source": "not-opened.pdf", "pages": [
            {"page": 1, "result": str(result_path)},
        ]}],
    })
    _save_json(result_path, {
        "schema_version": 1, "document_id": "doc-1", "page": 1, "month": "2026-06",
        "project": "项目A", "people": [person], "warnings": ["第1页有模糊标记"],
    })
    attendance["source_warnings"] = [{"document_id": "doc-1", "page": 1, "warning": "第1页有模糊标记"}]
    _save_json(workdir / "attendance.json", attendance)

    result = diagnose(workdir)

    assert result["missing_daily_day_count"] == 1
    assert result["source_warning_count"] == 1
    assert result["current_exception_count"] == len(analyze(attendance)["issues"])
    assert result["current_exception_count"] > 0


def test_diagnostics_never_appears_in_final_markdown(tmp_path):
    workdir = tmp_path / "work"
    result_path = workdir / ".attendance-pages/doc-1/page-1.json"
    attendance = _attendance(_person())
    _save_json(workdir / "attendance-manifest.json", {
        "schema_version": 1,
        "documents": [{"document_id": "doc-1", "source": "missing.pdf", "pages": [
            {"page": 1, "result": str(result_path)},
        ]}],
    })
    _save_json(result_path, {
        "schema_version": 1, "document_id": "doc-1", "page": 1, "month": "2026-06",
        "project": "项目A", "people": attendance["people"], "warnings": [],
    })
    _save_json(workdir / "attendance.json", attendance)
    diagnose(workdir)

    markdown, _ = render(attendance)
    assert ".attendance-diagnostics.json" not in markdown
    assert "preprocess_elapsed_ms" not in markdown
    assert "agent_image_read_call_count" not in markdown


def test_skill_documents_single_page_policy_and_runtime_boundary():
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    recognition = (SKILL_DIR / "references/recognition.md").read_text(encoding="utf-8")
    for text in (skill, recognition):
        assert "OCR" in text
        assert "裁图" in text
        assert "单调时钟" in text or "Runtime" in text
    assert "九步" in skill
    assert "attendance_diagnostics.py" in skill and "ok=true" in skill
