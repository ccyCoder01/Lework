#!/usr/bin/env python3
"""Persist one vision recognition result per PDF page, then build attendance.json.

Recognition is performed by the active multimodal Agent, never by this script.
The page snapshots are immutable once saved; future changes target attendance.json.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

STATUS = {"work", "rest", "comp_leave", "annual_leave", "personal_leave", "sick_leave", "absent", "maternity_leave", "other_paid_leave", "transfer", "departed", "unknown", "blank"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".tmp-", suffix=".json", delete=False) as tmp:
        tmp.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = Path(tmp.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def checked_manifest(workdir: Path):
    workdir = workdir.resolve()
    manifest = load_json(workdir / "attendance-manifest.json")
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("documents"), list) or not manifest["documents"]:
        raise ValueError("无效任务清单")
    view_version = manifest.get("view_schema_version")
    if view_version in {2, 3}:
        if view_version == 3 and manifest.get("preprocess_version") != 3:
            raise ValueError("视图清单预处理版本无效")
        if view_version == 3 and (
            not isinstance(manifest.get("preprocess_config"), dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("preprocess_config_sha256", "")))
        ):
            raise ValueError("预处理参数摘要无效")
        if view_version == 3:
            config_hash = hashlib.sha256(json.dumps(
                manifest["preprocess_config"], sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            if config_hash != manifest["preprocess_config_sha256"]:
                raise ValueError("预处理参数内容与摘要不一致")
        seen_view_ids = set()
        for document in manifest["documents"]:
            if not isinstance(document, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(document.get("source_sha256", ""))):
                raise ValueError("视图清单缺少有效来源摘要")
            pages = document.get("pages")
            if not isinstance(pages, list) or not pages:
                raise ValueError("视图清单缺少页面")
            page_numbers = []
            for page in pages:
                if not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] < 1:
                    raise ValueError("视图清单页码无效")
                page_numbers.append(page["page"])
                if view_version == 3:
                    deskew = page.get("deskew")
                    if (not isinstance(deskew, dict) or type(deskew.get("applied")) is not bool
                            or not isinstance(deskew.get("algorithm"), str)
                            or deskew.get("algorithm") != "bounded_horizontal_projection_v1"
                            or type(deskew.get("confidence")) not in {int, float}
                            or not 0 <= deskew["confidence"] <= 1
                            or not isinstance(deskew.get("source_size"), list)
                            or not isinstance(deskew.get("output_size"), list)):
                        raise ValueError("页面纠偏元数据无效")
                views = page.get("views")
                if not isinstance(views, list) or not 2 <= len(views) <= 4:
                    raise ValueError(f"{document['document_id']}/page-{page['page']} 视图数必须为 2–4")
                if page.get("source_sha256") != document["source_sha256"]:
                    raise ValueError("页面来源摘要与文档不一致")
                if (
                    type(page.get("detail_width")) is not int
                    or type(page.get("detail_height")) is not int
                    or page["detail_width"] <= 0
                    or page["detail_height"] <= 0
                ):
                    raise ValueError("页面高分辨率尺寸无效")
                if not isinstance(page.get("result"), str) or not isinstance(page.get("image"), str):
                    raise ValueError("页面结果或概览图路径无效")
                for value in (page["result"], page["image"]):
                    candidate = Path(value)
                    if not candidate.is_absolute():
                        candidate = workdir / candidate
                    if not candidate.resolve().is_relative_to(workdir):
                        raise ValueError("页面输出路径超出当前任务工作目录")
                if not isinstance(views[0], dict) or views[0].get("view_type") != "overview":
                    raise ValueError("视图顺序必须先布局概览，再列人员行分区")
                overview_count = partition_count = 0
                core_regions = []
                for view in views:
                    if not isinstance(view, dict):
                        raise ValueError("视图条目无效")
                    view_id = view.get("view_id")
                    if not isinstance(view_id, str) or view_id in seen_view_ids:
                        raise ValueError("view_id 缺失或重复")
                    seen_view_ids.add(view_id)
                    if view.get("document_id") != document["document_id"] or view.get("page") != page["page"]:
                        raise ValueError("视图来源页绑定不一致")
                    if view.get("source_sha256") != document["source_sha256"]:
                        raise ValueError("视图来源摘要不一致")
                    if not re.fullmatch(r"[0-9a-f]{64}", str(view.get("image_sha256", ""))):
                        raise ValueError("视图缺少有效图片摘要")
                    view_path = Path(view.get("image", ""))
                    if not view_path.is_absolute():
                        view_path = workdir / view_path
                    if not view_path.resolve().is_relative_to(workdir):
                        raise ValueError("视图图片路径超出当前任务工作目录")
                    expected_range = view.get("expected_row_range")
                    if expected_range is not None and (
                        not isinstance(expected_range, list)
                        or len(expected_range) != 2
                        or any(type(value) is not int or value < 1 for value in expected_range)
                        or expected_range[0] > expected_range[1]
                    ):
                        raise ValueError("expected_row_range 格式无效")
                    if view.get("view_type") == "overview":
                        overview_count += 1
                        if view.get("recognition_role") != "layout_only_no_business_fact_extraction":
                            raise ValueError("概览视图角色无效")
                        if view.get("image") != page["image"]:
                            raise ValueError("概览图与兼容 image 路径不一致")
                    elif view.get("view_type") == "row_partition":
                        partition_count += 1
                        if view.get("recognition_role") != "primary_rows_by_printed_row_index":
                            raise ValueError("人员行视图角色无效")
                        region, core = view.get("region"), view.get("core_region")
                        if not isinstance(region, dict) or not isinstance(core, dict):
                            raise ValueError("人员行视图缺少裁切或核心区域")
                        coordinates = [region.get("y0"), region.get("y1"), core.get("y0"), core.get("y1")]
                        if any(type(value) is not int for value in coordinates):
                            raise ValueError("人员行视图坐标必须为整数")
                        if not (0 <= region.get("y0", -1) <= core.get("y0", -1) < core.get("y1", -1) <= region.get("y1", -1) <= page["detail_height"]):
                            raise ValueError("人员行视图区域边界无效")
                        if region.get("x0") != 0 or region.get("x1") != page["detail_width"] or core.get("x0") != 0 or core.get("x1") != page["detail_width"]:
                            raise ValueError("人员行视图必须保留完整页面宽度")
                        core_regions.append((core["y0"], core["y1"]))
                    else:
                        raise ValueError("未知视图类型")
                if overview_count != 1 or not 1 <= partition_count <= 3:
                    raise ValueError("每页必须有一张概览和一至三张人员行视图")
                if core_regions[0][0] >= core_regions[0][1] or any(
                    left[1] != right[0] for left, right in zip(core_regions, core_regions[1:])
                ):
                    raise ValueError("人员行视图核心区域必须有序且无遗漏/重叠")
            if sorted(page_numbers) != list(range(1, len(page_numbers) + 1)):
                raise ValueError("视图清单页码必须连续")
    return manifest


def page_descriptor(manifest: dict, document_id: str, page_number: int):
    for doc in manifest["documents"]:
        if doc["document_id"] == document_id:
            for p in doc["pages"]:
                if p["page"] == page_number:
                    return doc, p
    raise ValueError(f"清单中不存在页面 {document_id}/page-{page_number}")


def validate_page(result: dict, doc: dict, p: dict, view_version: int = 1):
    if not isinstance(result, dict) or result.get("schema_version") != 1:
        raise ValueError("识别结果缺少 schema_version=1")
    if result.get("document_id") != doc["document_id"] or result.get("page") != p["page"]:
        raise ValueError("文档或页码与清单不一致")
    month = result.get("month")
    import re
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("月份必须为 YYYY-MM")
    if not isinstance(result.get("project"), str):
        raise ValueError("project 必须为字符串，无法识别可为空字符串")
    people = result.get("people")
    if not isinstance(people, list):
        raise ValueError("people 必须为数组，无法识别时为空数组并保留 warnings")
    import calendar
    yy, mm = map(int, month.split("-"))
    max_day = calendar.monthrange(yy, mm)[1]
    requires_row_index = any(
        isinstance(view, dict) and view.get("recognition_role") == "primary_rows_by_printed_row_index"
        for view in p.get("views", [])
    )
    row_indices = []
    row_views = {
        view.get("view_id"): view for view in p.get("views", [])
        if isinstance(view, dict) and view.get("view_type") == "row_partition"
    }
    for index, person in enumerate(people):
        if not isinstance(person, dict) or not isinstance(person.get("name"), str) or not person["name"].strip():
            raise ValueError(f"people[{index}] 缺少姓名；不清晰时使用明确的占位名并标记不确定")
        if not isinstance(person.get("daily"), list):
            raise ValueError(f"people[{index}] daily 必须为数组")
        row_index = person.get("row_index")
        row_status = person.get("row_binding_status")
        if row_status is not None and (
            not isinstance(row_status, str) or row_status not in {"VERIFIED", "UNRESOLVED", "CONFLICT"}
        ):
            raise ValueError(f"people[{index}] row_binding_status 无效")
        if row_index is not None:
            if type(row_index) is not int or row_index < 1:
                raise ValueError(f"people[{index}] row_index 必须为正整数")
            row_indices.append(row_index)
        if row_index is None and requires_row_index and row_status != "UNRESOLVED":
            raise ValueError(f"people[{index}] 缺少行索引且未标记行绑定待核")
        if view_version == 3 and row_index is not None:
            source_view_id = person.get("source_view_id")
            source_view = row_views.get(source_view_id) if isinstance(source_view_id, str) else None
            if source_view is None:
                raise ValueError(f"people[{index}] row_index 必须绑定清单中的 source_view_id")
            expected_range = source_view.get("expected_row_range")
            if expected_range is not None and not expected_range[0] <= row_index <= expected_range[1]:
                raise ValueError(f"people[{index}] row_index 不属于 source_view_id 的预期行范围")
        if row_status == "VERIFIED" and row_index is None:
            raise ValueError(f"people[{index}] VERIFIED 行绑定必须有 row_index")
        if requires_row_index and row_index is None and row_status == "UNRESOLVED":
            if not isinstance(person.get("row_binding_warning"), str) or not person["row_binding_warning"].strip():
                raise ValueError(f"people[{index}] 行绑定待核时必须提供 row_binding_warning")
        seen = set()
        for d in person["daily"]:
            if not isinstance(d, dict) or type(d.get("day")) is not int or not 1 <= d["day"] <= max_day:
                raise ValueError(f"people[{index}] 包含无效日期")
            if d["day"] in seen:
                raise ValueError(f"people[{index}] 日考勤重复")
            seen.add(d["day"])
            if not isinstance(d.get("raw_mark"), str) or d.get("status") not in STATUS:
                raise ValueError(f"people[{index}] 日期{d['day']} 的 raw_mark/status 无效")
        missing_days = person.get("missing_days", [])
        if not isinstance(missing_days, list) or any(type(day) is not int or not 1 <= day <= max_day for day in missing_days):
            raise ValueError(f"people[{index}] missing_days 无效")
        if len(missing_days) != len(set(missing_days)):
            raise ValueError(f"people[{index}] missing_days 重复")
        actual_missing = set(range(1, max_day + 1)) - seen
        if requires_row_index and actual_missing != set(missing_days):
            raise ValueError(f"people[{index}] 缺失日期必须在 missing_days 中逐日声明")
        for field in ("printed_work_days", "position", "note"):
            if field in person and person[field] is not None and not isinstance(person[field], (str, int, float)):
                raise ValueError(f"people[{index}] {field} 类型错误")
        if "printed_work_days_row_index" in person and person["printed_work_days_row_index"] is not None and (
            type(person["printed_work_days_row_index"]) is not int or person["printed_work_days_row_index"] < 1
        ):
            raise ValueError(f"people[{index}] printed_work_days_row_index 必须为正整数或 null")
        if "note_row_index" in person and person["note_row_index"] is not None and (
            type(person["note_row_index"]) is not int or person["note_row_index"] < 1
        ):
            raise ValueError(f"people[{index}] note_row_index 必须为正整数或 null")
        if view_version == 3:
            if person.get("printed_work_days") not in (None, "") and person.get("printed_work_days_row_index") != row_index:
                raise ValueError(f"people[{index}] 印刷出勤必须明确绑定到同一 row_index")
            if str(person.get("note", "")).strip() and person.get("note_row_index") != row_index:
                raise ValueError(f"people[{index}] 备注必须明确绑定到同一 row_index")
    if len(row_indices) != len(set(row_indices)):
        raise ValueError("页级人员 row_index 重复，可能存在重叠视图行重复或绑定错误")
    warnings = result.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(w, str) for w in warnings):
        raise ValueError("warnings 必须为字符串数组")
    quality_warnings = result.get("quality_warnings", [])
    if not isinstance(quality_warnings, list) or any(not isinstance(warning, str) for warning in quality_warnings):
        raise ValueError("quality_warnings 必须为字符串数组")


def save_page(workdir: Path, result_file: Path):
    manifest = checked_manifest(workdir)
    result = load_json(result_file)
    doc, p = page_descriptor(manifest, result.get("document_id"), result.get("page"))
    validate_page(result, doc, p, manifest.get("view_schema_version", 1))
    if any(view.get("view_type") == "row_partition" for view in p.get("views", [])):
        for view in p["views"]:
            image_path = Path(view["image"]).resolve()
            if image_path.is_symlink() or not image_path.is_file():
                raise ValueError(f"固定识别视图缺失或不是普通文件: {image_path}")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if digest != view["image_sha256"]:
                raise ValueError(f"固定识别视图摘要不一致: {view['view_id']}")
    result = copy.deepcopy(result)
    result.setdefault("quality_warnings", [])
    if p.get("view_status") == "LIMITED":
        result["quality_warnings"].append("预处理未能稳定定位页面内容区域；本页识别质量受限，需人工核对")
    row_indices = [person["row_index"] for person in result["people"] if type(person.get("row_index")) is int]
    if row_indices and sorted(row_indices) != list(range(min(row_indices), max(row_indices) + 1)):
        result["quality_warnings"].append("人员行索引存在缺号，需核实是否漏人")
    for person in result["people"]:
        if person.get("row_binding_status") in {"UNRESOLVED", "CONFLICT"}:
            result["quality_warnings"].append(
                f"人员行绑定待核：row_index={person.get('row_index')}，{person.get('row_binding_warning', '')}".strip()
            )
        try:
            printed = int(str(person.get("printed_work_days")).strip())
        except (TypeError, ValueError):
            printed = None
        if printed is not None:
            observed = sum(1 for item in person["daily"] if item.get("status") == "work")
            if printed != observed:
                result["quality_warnings"].append(
                    f"人员行{person.get('row_index', '?')} 印刷实际出勤{printed}，逐日观察work计数{observed}，保留原值待核"
                )
        if person.get("missing_days"):
            result["quality_warnings"].append(
                f"人员行{person.get('row_index', '?')} 缺少逐日记录：{','.join(map(str, person['missing_days']))}日"
            )
    target = Path(p["result"])
    if target.exists():
        raise ValueError(f"页面已保存，不可覆盖或再次识别: {target}")
    atomic_json(target, result)
    return {"ok": True, "saved": str(target)}


def status(workdir: Path):
    manifest = checked_manifest(workdir)
    found, missing, invalid = [], [], []
    for doc in manifest["documents"]:
        for p in doc["pages"]:
            path = Path(p["result"])
            key = f"{doc['document_id']}/page-{p['page']}"
            if not path.exists():
                missing.append(key)
            else:
                try:
                    validate_page(load_json(path), doc, p, manifest.get("view_schema_version", 1))
                    found.append(key)
                except (ValueError, json.JSONDecodeError) as exc:
                    invalid.append({"page": key, "error": str(exc)})
    return {"ok": not missing and not invalid, "saved": found, "missing": missing, "invalid": invalid}


def assemble(workdir: Path):
    state = status(workdir)
    if not state["ok"]:
        raise ValueError(f"仍有未保存/无效页：{state['missing']} {state['invalid']}")
    output = workdir / "attendance.json"
    if output.exists():
        raise ValueError("attendance.json 已存在，不允许从原始识别缓存覆盖已修改的工作数据")
    manifest = checked_manifest(workdir)
    months, people, source_warnings = set(), [], []
    for doc in manifest["documents"]:
        for p in doc["pages"]:
            page = load_json(Path(p["result"]))
            months.add(page["month"])
            source_warnings.extend(
                {"document_id": doc["document_id"], "page": p["page"], "warning": warning}
                for warning in page.get("warnings", [])
            )
            source_warnings.extend(
                {"document_id": doc["document_id"], "page": p["page"], "warning": warning, "kind": "recognition_quality"}
                for warning in page.get("quality_warnings", [])
            )
            for idx, person in enumerate(page["people"], 1):
                item = copy.deepcopy(person)
                stable_row = item.get("row_index")
                item["record_id"] = f"{doc['document_id']}-p{p['page']}-r{stable_row if stable_row is not None else idx}"
                item["source_document"] = doc["source"]
                item["source_page"] = p["page"]
                item["project"] = page["project"]
                people.append(item)
    if len(months) != 1:
        raise ValueError(f"考勤月份冲突，禁止合并: {sorted(months)}")
    if not people:
        raise ValueError("没有可识别的考勤人员")
    payload = {"schema_version": 1, "month": next(iter(months)), "people": people, "source_warnings": source_warnings}
    atomic_json(output, payload)
    return {"ok": True, "output": str(output), "people_records": len(people), "month": payload["month"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["save-page", "status", "assemble"])
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--result", type=Path, help="save-page 时指定模型识别的单页 JSON 文件")
    args = parser.parse_args()
    try:
        wd = args.workdir.expanduser().resolve()
        if args.command == "save-page":
            if args.result is None:
                raise ValueError("save-page 需要 --result")
            obj = save_page(wd, args.result)
        elif args.command == "status":
            obj = status(wd)
        else:
            obj = assemble(wd)
        print(json.dumps(obj, ensure_ascii=False))
        if args.command == "status" and not obj["ok"]:
            raise SystemExit(3)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
