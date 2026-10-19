import json
import sys
import calendar
from pathlib import Path

import fitz
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from pdf_prepare import prepare
from attendance_store import save_page, status, assemble


def pdf_file(path, pages=2):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=800, height=500)
        page.insert_text((50, 50), "attendance")
    doc.save(path)
    doc.close()


def write_page(path, doc="doc-1", page=1, month="2026-06"):
    year, month_number = map(int, month.split("-"))
    day_count = calendar.monthrange(year, month_number)[1]
    path.write_text(json.dumps({
        "schema_version": 1, "document_id": doc, "page": page, "month": month,
        "project": "项目A", "people": [{"row_index": 1, "name": "张三", "position": "施工员", "printed_work_days": "1",
        "daily": [{"day": day, "raw_mark": "8" if day == 1 else "", "status": "work" if day == 1 else "blank"}
                  for day in range(1, day_count + 1)]}], "warnings": [],
    }, ensure_ascii=False), encoding="utf-8")


def test_page_save_assemble_and_no_overwrite(tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf_file(pdf)
    result = prepare([pdf], tmp_path / "run")
    assert result["total_pages"] == 2
    wd = tmp_path / "run"
    assert status(wd)["missing"] == ["doc-1/page-1", "doc-1/page-2"]
    for n in (1, 2):
        source = tmp_path / f"page-{n}.json"
        write_page(source, page=n)
        if n == 1:
            page_data = json.loads(source.read_text(encoding="utf-8"))
            page_data["warnings"] = ["第 1 页人员行待核"]
            source.write_text(json.dumps(page_data, ensure_ascii=False), encoding="utf-8")
        save_page(wd, source)
        with pytest.raises(ValueError, match="不可覆盖"):
            save_page(wd, source)
    assert status(wd)["ok"]
    assembled = assemble(wd)
    assert assembled["people_records"] == 2
    people = json.loads((wd / "attendance.json").read_text(encoding="utf-8"))["people"]
    assert people[0]["source_page"] == 1
    data = json.loads((wd / "attendance.json").read_text(encoding="utf-8"))
    assert data["source_warnings"] == [{"document_id": "doc-1", "page": 1, "warning": "第 1 页人员行待核"}]
    with pytest.raises(ValueError, match="已存在"):
        assemble(wd)


def test_invalid_record_not_saved(tmp_path):
    pdf = tmp_path / "test.pdf"
    pdf_file(pdf, pages=1)
    wd = tmp_path / "run"
    prepare([pdf], wd)
    source = tmp_path / "invalid.json"
    write_page(source)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["people"][0]["daily"][0]["status"] = "invented"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="无效"):
        save_page(wd, source)
    assert not (wd / ".attendance-pages/doc-1/page-1.json").exists()


def test_conflicting_month_blocks_assembly(tmp_path):
    p1, p2 = tmp_path / "first.pdf", tmp_path / "second.pdf"
    pdf_file(p1, pages=1)
    pdf_file(p2, pages=1)
    wd = tmp_path / "run"
    prepare([p1, p2], wd)
    for d, month in [("doc-1", "2026-06"), ("doc-2", "2026-05")]:
        src = tmp_path / f"{d}.json"
        write_page(src, doc=d, month=month)
        save_page(wd, src)
    with pytest.raises(ValueError, match="月份冲突"):
        assemble(wd)
