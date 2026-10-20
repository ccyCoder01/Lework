#!/usr/bin/env python3
"""Summarize existing attendance recognition data without opening source PDFs or images."""
from __future__ import annotations

import argparse
import calendar
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from attendance_review import analyze
from attendance_store import checked_manifest, load_json, validate_page


def _work_file(workdir: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = workdir / path
    resolved = path.resolve()
    if not resolved.is_relative_to(workdir.resolve()):
        raise ValueError("清单中的识别结果路径超出当前工作目录")
    return resolved


def _save_summary(path: Path, summary: dict) -> None:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".diagnostics-", suffix=".tmp", delete=False) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def diagnose(workdir: Path) -> dict:
    """Read manifests and JSON snapshots only; never open the PDF or page images."""
    workdir = workdir.expanduser().resolve()
    manifest = checked_manifest(workdir)
    documents = manifest["documents"]
    page_rows, missing_pages, invalid_pages = [], [], []
    total_view_count = overview_count = partition_count = 0
    missing_row_index_count = duplicate_row_index_count = row_binding_anomaly_count = 0
    printed_daily_mismatch_count = 0
    page_view_details = []
    page_count = 0
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("pages"), list):
            raise ValueError("attendance-manifest.json 中的文档或页面清单无效")
        document_id = document.get("document_id")
        for page in document["pages"]:
            page_count += 1
            if not isinstance(page, dict) or type(page.get("page")) is not int or not isinstance(page.get("result"), str):
                invalid_pages.append({"document_id": document_id, "page": None, "error": "页面清单字段无效"})
                continue
            key = f"{document_id}/page-{page['page']}"
            views = page.get("views", [])
            if not isinstance(views, list):
                invalid_pages.append({"page": key, "error": "views 必须为数组"})
                continue
            view_ids = [view.get("view_id") for view in views if isinstance(view, dict)]
            if len(views) > 4 or len(view_ids) != len(views) or len(set(view_ids)) != len(view_ids):
                invalid_pages.append({"page": key, "error": "视图数量、结构或 view_id 唯一性无效"})
                continue
            page_overviews = sum(view.get("view_type") == "overview" for view in views if isinstance(view, dict))
            page_partitions = sum(view.get("view_type") == "row_partition" for view in views if isinstance(view, dict))
            total_view_count += len(views)
            overview_count += page_overviews
            partition_count += page_partitions
            page_view_details.append({
                "document_id": document_id,
                "page": page["page"],
                "view_count": len(views),
                "overview_count": page_overviews,
                "partition_count": page_partitions,
                "view_status": page.get("view_status"),
                "expected_row_ranges": [
                    {"view_id": view.get("view_id"), "range": view.get("expected_row_range")}
                    for view in views if isinstance(view, dict) and view.get("view_type") == "row_partition"
                ],
            })
            try:
                result_path = _work_file(workdir, page["result"])
            except ValueError as exc:
                invalid_pages.append({"page": key, "error": str(exc)})
                continue
            if not result_path.is_file():
                missing_pages.append(key)
                continue
            try:
                result = load_json(result_path)
                people = result.get("people", []) if isinstance(result, dict) else []
                row_required = any(
                    isinstance(view, dict) and view.get("recognition_role") == "primary_rows_by_printed_row_index"
                    for view in views
                )
                indices = [person.get("row_index") for person in people if type(person.get("row_index")) is int]
                if row_required:
                    missing_row_index_count += sum(
                        1 for person in people if person.get("row_index") is None
                    )
                duplicate_row_index_count += len(indices) - len(set(indices))
                row_binding_anomaly_count += sum(
                    1 for person in people if person.get("row_binding_status") in {"UNRESOLVED", "CONFLICT"}
                )
                row_binding_anomaly_count += sum(
                    1 for warning in result.get("quality_warnings", [])
                    if "行绑定" in warning or "行索引" in warning or "漏人" in warning
                )
                for person in people:
                    try:
                        printed = int(str(person.get("printed_work_days")).strip())
                    except (TypeError, ValueError):
                        continue
                    observed = sum(1 for item in person.get("daily", []) if item.get("status") == "work")
                    if printed != observed:
                        printed_daily_mismatch_count += 1
                validate_page(result, document, page, manifest.get("view_schema_version", 1))
                page_rows.append({
                    "document_id": document_id,
                    "page": page["page"],
                    "people_count": len(people),
                })
                page_view_details[-1]["row_binding_details"] = {
                    "row_indices": indices,
                    "duplicate_row_indices": sorted({index for index in indices if indices.count(index) > 1}),
                }
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                invalid_pages.append({"page": key, "error": str(exc)})

    runtime_path = workdir / ".attendance-runtime.json"
    preprocess_ms = None
    rendered_images = reused_images = preprocess_invocations = None
    rendered_views = reused_views = overview_views = partition_views = None
    runtime_status = "unavailable"
    if runtime_path.is_file():
        try:
            runtime = load_json(runtime_path)
            if runtime.get("schema_version") == 1 and isinstance(runtime.get("events"), list):
                events = [event for event in runtime["events"] if isinstance(event, dict) and event.get("stage") == "pdf_prepare"]
                if events:
                    measured = [
                        event for event in events
                        if isinstance(event.get("elapsed_ms"), (int, float))
                        and not isinstance(event.get("elapsed_ms"), bool)
                    ]
                    if len(measured) == len(events):
                        preprocess_ms = sum(event["elapsed_ms"] for event in measured)
                        preprocess_invocations = len(measured)
                        rendered_images = sum(
                            event.get("rendered_page_images", 0)
                            for event in measured
                            if isinstance(event.get("rendered_page_images", 0), int)
                            and not isinstance(event.get("rendered_page_images", 0), bool)
                        )
                        reused_images = sum(
                            event.get("reused_page_images", 0)
                            for event in measured
                            if isinstance(event.get("reused_page_images", 0), int)
                            and not isinstance(event.get("reused_page_images", 0), bool)
                        )
                        rendered_views = sum(
                            event.get("rendered_view_images", 0)
                            for event in measured
                            if isinstance(event.get("rendered_view_images", 0), int)
                            and not isinstance(event.get("rendered_view_images", 0), bool)
                        )
                        reused_views = sum(
                            event.get("reused_view_images", 0)
                            for event in measured
                            if isinstance(event.get("reused_view_images", 0), int)
                            and not isinstance(event.get("reused_view_images", 0), bool)
                        )
                        overview_views = sum(event.get("overview_view_count", 0) for event in measured)
                        partition_views = sum(event.get("row_partition_view_count", 0) for event in measured)
                        runtime_status = "measured_by_monotonic_clock"
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            runtime_status = "invalid"

    attendance_path = workdir / "attendance.json"
    attendance_status = "missing"
    record_count = unknown_status_count = raw_unknown_status_count = missing_day_count = source_warning_count = None
    exception_count = None
    attendance_error = None
    if attendance_path.is_file():
        try:
            attendance = load_json(attendance_path)
            report = analyze(attendance)
            people = attendance["people"]
            year, month = map(int, attendance["month"].split("-"))
            days_in_month = calendar.monthrange(year, month)[1]
            record_count = len(people)
            raw_unknown_status_count = sum(
                1 for person in people for item in person.get("daily", []) if item.get("status") == "unknown"
            )
            unknown_status_count = sum(
                1 for person in people for item in person.get("daily", [])
                if item.get("user_confirmed_status", item.get("status")) == "unknown"
            )
            missing_day_count = sum(
                len(set(range(1, days_in_month + 1)) - {item["day"] for item in person.get("daily", [])})
                for person in people
            )
            source_warning_count = len(attendance.get("source_warnings", []))
            exception_count = len(report["issues"])
            attendance_status = "valid"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            attendance_status = "invalid"
            attendance_error = str(exc)

    page_people_count = sum(row["people_count"] for row in page_rows)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workdir": str(workdir),
        "pdf_count": len(documents),
        "pdf_page_count": page_count,
        "view_count": total_view_count,
        "overview_view_count": overview_count,
        "row_partition_view_count": partition_count,
        "page_view_details": page_view_details,
        "page_people_counts": page_rows,
        "page_people_record_count": page_people_count,
        "saved_page_count": len(page_rows),
        "missing_page_count": len(missing_pages),
        "invalid_page_count": len(invalid_pages),
        "missing_pages": missing_pages,
        "invalid_pages": invalid_pages,
        "missing_row_index_count": missing_row_index_count,
        "duplicate_row_index_count": duplicate_row_index_count,
        "row_binding_anomaly_count": row_binding_anomaly_count,
        "printed_daily_mismatch_count": printed_daily_mismatch_count,
        "attendance_status": attendance_status,
        "attendance_record_count": record_count,
        "raw_unknown_status_count": raw_unknown_status_count,
        "current_unknown_status_count": unknown_status_count,
        "missing_daily_day_count": missing_day_count,
        "source_warning_count": source_warning_count,
        "current_exception_count": exception_count,
        "attendance_error": attendance_error,
        "timing": {
            "preprocess_elapsed_ms": preprocess_ms,
            "preprocess_timing_status": runtime_status,
            "preprocess_invocation_count": preprocess_invocations,
            "preprocess_rendered_page_images": rendered_images,
            "preprocess_reused_page_images": reused_images,
            "preprocess_rendered_view_images": rendered_views,
            "preprocess_reused_view_images": reused_views,
            "preprocess_overview_view_count": overview_views,
            "preprocess_row_partition_view_count": partition_views,
            "model_inference_ms": None,
            "agent_image_read_call_count": None,
        },
    }
    _save_summary(workdir / ".attendance-diagnostics.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(diagnose(args.workdir), ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
