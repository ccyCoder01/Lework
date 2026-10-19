import json
import sys
from pathlib import Path

import pytest
import fitz
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from attendance_review import analyze  # noqa: E402
from pdf_prepare import _deskew, prepare  # noqa: E402


def _tilted_table(angle=1.2):
    image = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(image)
    for y in range(35, 480, 20):
        draw.line((20, y, 880, y), fill="black", width=2)
    for x in range(20, 881, 30):
        draw.line((x, 20, x, 480), fill="black", width=1)
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")


def _person(record_id, row, printed, *, binding="VERIFIED", confirmed=None, daily_work=20):
    person = {
        "record_id": record_id,
        "name": record_id,
        "project": "项目甲",
        "source_document": "attendance.pdf",
        "source_page": 2,
        "row_index": row,
        "row_binding_status": binding,
        "printed_work_days": str(printed),
        "printed_work_days_row_index": row if binding == "VERIFIED" else None,
        "daily": [
            {"day": day, "raw_mark": "8" if day <= daily_work else "休",
             "status": "work" if day <= daily_work else "rest"}
            for day in range(1, 31)
        ],
    }
    if confirmed is not None:
        person["confirmed_work_days"] = confirmed
    return person


def _review_data(people):
    return {"schema_version": 1, "month": "2026-06", "people": people, "source_warnings": []}


def test_bounded_deskew_corrects_small_skew_without_cropping():
    image = _tilted_table()
    corrected, meta = _deskew(image)
    assert meta["applied"] is True
    assert meta["detected_angle_degrees"] == pytest.approx(-1.2, abs=0.11)
    assert corrected.width >= image.width and corrected.height >= image.height
    assert meta["output_size"] == list(corrected.size)


def test_horizontal_table_is_not_rotated():
    image = _tilted_table(0)
    corrected, meta = _deskew(image)
    assert corrected is image
    assert meta["detected_angle_degrees"] == 0
    assert meta["applied"] is False


def test_deskew_failure_keeps_original_image(monkeypatch):
    import pdf_prepare

    image = _tilted_table()
    monkeypatch.setattr(pdf_prepare, "_alignment_score", lambda _image, _angle: (_ for _ in ()).throw(RuntimeError()))
    corrected, meta = pdf_prepare._deskew(image)
    assert corrected is image
    assert meta["applied"] is False
    assert meta["reason"] == "correction_failed:RuntimeError"


def test_deskew_below_minimum_angle_never_rotates_even_with_score_gain(monkeypatch):
    import pdf_prepare

    image = _tilted_table(0)
    monkeypatch.setattr(pdf_prepare, "_alignment_score", lambda _image, angle: 1.02 if angle == 0.3 else 1.0)
    corrected, meta = pdf_prepare._deskew(image)
    assert corrected is image
    assert meta["detected_angle_degrees"] == pytest.approx(0.3)
    assert meta["applied"] is False
    assert meta["reason"] == "angle_below_threshold"


def test_verified_printed_value_takes_priority_and_daily_mismatch_is_reported():
    report = analyze(_review_data([_person("r40", 40, 28, daily_work=27)]))
    stats = report["stats"]["r40"]
    assert stats["actual_work_days"] == 28
    assert stats["observed_work_days"] == 27
    assert any(issue.get("printed") == 28 and issue.get("daily") == 27 for issue in report["issues"])


def test_user_confirmed_total_overrides_printed_source_without_erasing_it():
    report = analyze(_review_data([_person("r41", 41, 28, confirmed=27, daily_work=26)]))
    assert report["stats"]["r41"]["actual_work_days"] == 27
    assert report["stats"]["r41"]["observed_work_days"] == 26
    assert any(issue.get("printed") == 28 and issue.get("daily") == 26 for issue in report["issues"])


def test_unverified_print_row_is_not_attributed_to_person():
    report = analyze(_review_data([_person("r42", 42, 15, binding="UNRESOLVED")]))
    assert report["stats"]["r42"]["actual_work_days"] == "待确认"
    assert any(issue.get("reason") == "印刷出勤行绑定待确认" for issue in report["issues"])


def test_missing_printed_value_is_pending_even_if_daily_marks_are_countable():
    person = _person("r43", 43, 20)
    person.pop("printed_work_days")
    person.pop("printed_work_days_row_index")
    report = analyze(_review_data([person]))
    assert report["stats"]["r43"]["actual_work_days"] == "待确认"
    assert report["stats"]["r43"]["observed_work_days"] == 20


def test_print_priority_does_not_change_explicit_absence_counting():
    person = _person("r44", 44, 25, daily_work=25)
    person["daily"][0] = {"day": 1, "raw_mark": "旷", "status": "absent"}
    person["daily"][1] = {"day": 2, "raw_mark": "病", "status": "sick_leave"}
    person["daily"][2] = {"day": 3, "raw_mark": "休", "status": "rest"}
    person["daily"][3] = {"day": 4, "raw_mark": "换", "status": "comp_leave"}
    report = analyze(_review_data([person]))
    assert report["stats"]["r44"]["actual_work_days"] == 25
    assert report["stats"]["r44"]["absence_days"] == 2


def test_changed_preprocessing_configuration_rejects_cached_views(tmp_path):
    source = tmp_path / "page.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "attendance row")
    doc.save(source)
    doc.close()
    workdir = tmp_path / "work"
    prepare([source], workdir)
    manifest_path = workdir / "attendance-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["preprocess_config"]["deskew"]["minimum_score_gain"] = 0.99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="预处理参数"):
        prepare([source], workdir)


def test_duplicate_row_binding_on_same_source_page_is_rejected():
    with pytest.raises(ValueError, match="重复绑定 row_index"):
        analyze(_review_data([_person("a", 42, 15), _person("b", 42, 26)]))


def test_hanyue_final_rows_fixture_preserves_row_values_independently():
    # Synthetic contract fixture only; these are not asserted as historical PDF truth.
    people = [
        _person("lu", 40, 28, daily_work=27),
        _person("cheng", 41, 15, daily_work=15),
        _person("xiong", 42, 26, daily_work=26),
    ]
    report = analyze(_review_data(people))
    assert [report["stats"][person["record_id"]]["actual_work_days"] for person in people] == [28, 15, 26]
    assert [person["printed_work_days_row_index"] for person in people] == [40, 41, 42]
