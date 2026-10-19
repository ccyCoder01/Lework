#!/usr/bin/env python3
"""Validate and apply explicit user corrections to attendance.json."""
from __future__ import annotations

import argparse
import calendar
import copy
import json
from pathlib import Path

from attendance_store import STATUS, atomic_json, load_json

ABSENCE_STATUSES = {
    "annual_leave", "personal_leave", "sick_leave", "absent",
    "maternity_leave", "other_paid_leave",
}
UNRESOLVED_STATUSES = {"unknown", "blank", "transfer", "departed"}
RECOGNIZED_MARKS = {
    "": "blank", "8": "work", "√": "work", "休": "rest", "换": "comp_leave",
    "事": "personal_leave", "病": "sick_leave", "旷": "absent", "产": "maternity_leave",
}


def _validate_document(data: dict) -> tuple[int, list[dict]]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("attendance.json 必须为 schema_version=1 对象")
    month = data.get("month")
    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
        raise ValueError("month 必须为 YYYY-MM")
    try:
        year, month_number = map(int, month.split("-"))
        days_in_month = calendar.monthrange(year, month_number)[1]
    except (ValueError, TypeError):
        raise ValueError("month 必须为有效的 YYYY-MM") from None
    people = data.get("people")
    if not isinstance(people, list):
        raise ValueError("people 必须为数组")
    source_warnings = data.get("source_warnings", [])
    if not isinstance(source_warnings, list) or any(not isinstance(w, dict) or not isinstance(w.get("warning"), str) for w in source_warnings):
        raise ValueError("source_warnings 必须为包含 warning 字符串的数组")
    resolved_warnings = data.get("resolved_source_warnings", [])
    if (not isinstance(resolved_warnings, list)
            or any(not isinstance(ref, dict) or type(ref.get("warning_index")) is not int
                   or not 0 <= ref["warning_index"] < len(source_warnings)
                   or any(ref.get(key) != source_warnings[ref["warning_index"]].get(key)
                          for key in ("document_id", "page", "warning"))
                   for ref in resolved_warnings)
            or len({ref["warning_index"] for ref in resolved_warnings if isinstance(ref, dict) and type(ref.get("warning_index")) is int}) != len(resolved_warnings)):
        raise ValueError("resolved_source_warnings 必须绑定到未变更且不重复的 source_warnings 原文")
    seen_ids = set()
    page_rows = set()
    for i, person in enumerate(people):
        if not isinstance(person, dict):
            raise ValueError(f"people[{i}] 必须为对象")
        record_id = person.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError(f"people[{i}] 缺少稳定 record_id")
        if record_id in seen_ids:
            raise ValueError(f"record_id 不唯一: {record_id}")
        seen_ids.add(record_id)
        if "confirmed_work_days" in person and (type(person["confirmed_work_days"]) is not int or not 0 <= person["confirmed_work_days"] <= days_in_month):
            raise ValueError(f"{record_id} 的 confirmed_work_days 必须为 0..{days_in_month} 的整数")
        if "confirmed_person_id" in person:
            confirmed_person_id = person["confirmed_person_id"]
            if (not isinstance(confirmed_person_id, str) or not confirmed_person_id
                    or confirmed_person_id != confirmed_person_id.strip()):
                raise ValueError(f"{record_id} 的 confirmed_person_id 必须为无首尾空格的非空字符串")
        row_index = person.get("row_index")
        row_status = person.get("row_binding_status")
        if row_index is not None and (type(row_index) is not int or row_index < 1):
            raise ValueError(f"{record_id} 的 row_index 必须为正整数或 null")
        if row_status is not None and (
            not isinstance(row_status, str) or row_status not in {"VERIFIED", "UNRESOLVED", "CONFLICT"}
        ):
            raise ValueError(f"{record_id} 的 row_binding_status 无效")
        if row_status == "VERIFIED" and row_index is None:
            raise ValueError(f"{record_id} VERIFIED 行绑定必须有 row_index")
        source_document, source_page = person.get("source_document"), person.get("source_page")
        if source_page is not None:
            if not isinstance(source_document, str) or not source_document.strip() or type(source_page) is not int or source_page < 1:
                raise ValueError(f"{record_id} 的来源文档/页码绑定无效")
            if row_index is not None:
                page_row = (source_document, source_page, row_index)
                if page_row in page_rows:
                    raise ValueError(f"{record_id} 在同一来源页重复绑定 row_index={row_index}")
                page_rows.add(page_row)
        for field in ("printed_work_days_row_index", "note_row_index"):
            bound_index = person.get(field)
            if bound_index is not None and (type(bound_index) is not int or bound_index < 1):
                raise ValueError(f"{record_id} 的 {field} 必须为正整数或 null")
        if person.get("printed_work_days_row_index") is not None and person.get("printed_work_days_row_index") != row_index:
            raise ValueError(f"{record_id} 印刷出勤行号与人员行号不一致")
        if person.get("note_row_index") is not None and person.get("note_row_index") != row_index:
            raise ValueError(f"{record_id} 备注行号与人员行号不一致")
        daily = person.get("daily")
        if not isinstance(daily, list):
            raise ValueError(f"{record_id} 的 daily 必须为数组")
        days = set()
        for item in daily:
            if not isinstance(item, dict) or type(item.get("day")) is not int or not 1 <= item["day"] <= days_in_month:
                raise ValueError(f"{record_id} 包含无效的 daily 日期")
            if item["day"] in days:
                raise ValueError(f"{record_id} 第 {item['day']} 日重复")
            days.add(item["day"])
            if not isinstance(item.get("raw_mark"), str) or not isinstance(item.get("status"), str) or item["status"] not in STATUS:
                raise ValueError(f"{record_id} 第 {item['day']} 日 raw_mark/status 无效")
            if "user_confirmed_status" in item and (not isinstance(item["user_confirmed_status"], str) or item["user_confirmed_status"] not in STATUS):
                raise ValueError(f"{record_id} 第 {item['day']} 日 user_confirmed_status 无效")
            if "user_confirmed_mark" in item and not isinstance(item["user_confirmed_mark"], str):
                raise ValueError(f"{record_id} 第 {item['day']} 日 user_confirmed_mark 无效")
    return days_in_month, people


def _record_index(people: list[dict]) -> dict[str, dict]:
    return {person["record_id"]: person for person in people}


def _validate_operation(op: object, by_id: dict[str, dict], days_in_month: int, warning_count: int) -> tuple[str, object]:
    if not isinstance(op, dict):
        raise ValueError("每项操作必须为对象")
    if op.get("op") == "resolve_source_warning":
        index = op.get("warning_index")
        if type(index) is not int or not 0 <= index < warning_count:
            raise ValueError(f"warning_index 必须在 0..{warning_count - 1} 范围内")
        if op.get("confirm_resolved") is not True:
            raise ValueError("必须提供 confirm_resolved=true，表示用户明确确认该来源警告已处理")
        return "source_warning", index
    record_id = op.get("record_id")
    if not isinstance(record_id, str) or record_id not in by_id:
        raise ValueError(f"找不到 record_id: {record_id}")
    kind = op.get("op")
    if kind == "set_daily_status":
        day, status = op.get("day"), op.get("status")
        if type(day) is not int or not 1 <= day <= days_in_month:
            raise ValueError(f"{record_id} 的 day 必须在 1..{days_in_month}")
        if not isinstance(status, str) or status not in STATUS:
            raise ValueError(f"{record_id} 第 {day} 日 status 无效")
        if "confirmed_mark" in op and not isinstance(op["confirmed_mark"], str):
            raise ValueError(f"{record_id} 第 {day} 日 confirmed_mark 必须为字符串")
        return record_id, f"daily:{day}"
    if kind == "set_actual_work_days":
        value = op.get("value")
        if type(value) is not int or not 0 <= value <= days_in_month:
            raise ValueError(f"{record_id} 的实际出勤天数必须在 0..{days_in_month}")
        return record_id, "confirmed_work_days"
    raise ValueError(f"不支持的操作类型: {kind}")


def apply_operations(data: dict, request: dict) -> dict:
    """Validate a complete request before changing and atomically saving data."""
    days_in_month, people = _validate_document(data)
    operations = request.get("operations") if isinstance(request, dict) else None
    if not isinstance(operations, list) or not operations:
        raise ValueError("request.operations 必须为非空数组")
    by_id = _record_index(people)
    targets = set()
    for op in operations:
        target = _validate_operation(op, by_id, days_in_month, len(data.get("source_warnings", [])))
        if target in targets:
            raise ValueError(f"同一批次重复修改目标: {target[0]} {target[1]}")
        targets.add(target)

    updated = copy.deepcopy(data)
    resolved_warnings = {ref["warning_index"] for ref in updated.get("resolved_source_warnings", [])}
    for op in operations:
        if op["op"] == "resolve_source_warning":
            resolved_warnings.add(op["warning_index"])
    if resolved_warnings:
        updated["resolved_source_warnings"] = [
            {"warning_index": index, **{key: updated["source_warnings"][index][key]
                                        for key in ("document_id", "page", "warning")
                                        if key in updated["source_warnings"][index]}}
            for index in sorted(resolved_warnings)
        ]
    updated_by_id = _record_index(updated["people"])
    for op in operations:
        if op["op"] == "resolve_source_warning":
            continue
        person = updated_by_id[op["record_id"]]
        if op["op"] == "set_actual_work_days":
            person["confirmed_work_days"] = op["value"]
            continue
        day = op["day"]
        for item in person["daily"]:
            if item.get("day") == day:
                item["user_confirmed_status"] = op["status"]
                if "confirmed_mark" in op:
                    item["user_confirmed_mark"] = op["confirmed_mark"]
                break
        else:
            item = {"day": day, "raw_mark": "", "status": "blank", "user_confirmed_status": op["status"]}
            if "confirmed_mark" in op:
                item["user_confirmed_mark"] = op["confirmed_mark"]
            person["daily"].append(item)
        person["daily"].sort(key=lambda item: item.get("day", 0))
    return updated


def _person_stats(person: dict, days_in_month: int, month: str) -> tuple[dict, list[dict]]:
    issues = []
    daily_by_day = {}
    unresolved = False
    for item in person.get("daily", []):
        day = item.get("day")
        if type(day) is not int or day in daily_by_day:
            issues.append({"record_id": person["record_id"], "field": "daily", "reason": "日期无效或重复"})
            unresolved = True
            continue
        daily_by_day[day] = item
    missing = [day for day in range(1, days_in_month + 1) if day not in daily_by_day]
    if missing:
        issues.append({"record_id": person["record_id"], "field": "daily", "reason": "日期缺失", "days": missing})

    work_count, absence_count = 0, 0
    unresolved_absence = unresolved or bool(missing)
    for day, item in daily_by_day.items():
        status = _effective_status(item)
        if status == "work":
            work_count += 1
        elif status in ABSENCE_STATUSES:
            absence_count += 1
        elif status in UNRESOLVED_STATUSES or status not in STATUS:
            unresolved_absence = True
            issues.append({"record_id": person["record_id"], "field": f"{month}-{day:02d}", "reason": "状态待确认", "raw_mark": item.get("user_confirmed_mark", item.get("raw_mark", ""))})
        if status in {"transfer", "departed"}:
            unresolved_absence = True

    confirmed = person.get("confirmed_work_days")
    printed = person.get("printed_work_days")
    printed_count = None
    if printed is not None and str(printed).strip() != "":
        try:
            printed_count = int(str(printed).strip())
        except (TypeError, ValueError):
            issues.append({"record_id": person["record_id"], "field": "printed_work_days", "reason": "印刷出勤数无法解析", "value": printed})
        else:
            if not 0 <= printed_count <= days_in_month:
                issues.append({"record_id": person["record_id"], "field": "printed_work_days", "reason": "印刷出勤数超出当月范围", "value": printed})
                printed_count = None
    row_bound_print = (
        person.get("row_binding_status") == "VERIFIED"
        and type(person.get("row_index")) is int
        and person.get("printed_work_days_row_index") == person.get("row_index")
    )
    if printed_count is not None and not row_bound_print:
        issues.append({
            "record_id": person["record_id"], "field": "printed_work_days",
            "reason": "印刷出勤行绑定待确认",
        })
    if printed_count is not None and row_bound_print and printed_count != work_count:
        issues.append({"record_id": person["record_id"], "field": "printed_work_days", "reason": "印刷出勤与逐日统计不一致", "printed": printed_count, "daily": work_count})
    actual = confirmed if confirmed is not None else (printed_count if row_bound_print and printed_count is not None else "待确认")
    absence = "待确认" if unresolved_absence else absence_count
    return {"actual_work_days": actual, "absence_days": absence, "observed_work_days": work_count}, issues


def _effective_status(item: dict) -> str:
    """Return a confirmed status or a raw status backed by the fixed mark rules."""
    if "user_confirmed_status" in item:
        return item["user_confirmed_status"]
    status = item.get("status")
    if RECOGNIZED_MARKS.get(item.get("raw_mark", "").strip()) != status:
        return "unknown"
    return status


def analyze(data: dict) -> dict:
    days_in_month, people = _validate_document(data)
    stats, issues = {}, []
    for person in people:
        stat, found = _person_stats(person, days_in_month, data["month"])
        stats[person["record_id"]] = stat
        issues.extend(found)
        if not str(person.get("project", "")).strip():
            issues.append({"record_id": person["record_id"], "field": "project", "reason": "项目归属待确认"})
    resolved_warnings = {ref["warning_index"] for ref in data.get("resolved_source_warnings", [])}
    for index, warning in enumerate(data.get("source_warnings", [])):
        if index not in resolved_warnings:
            issues.append({"record_id": None, "field": f"{warning.get('document_id', '来源')}/page-{warning.get('page', '?')}", "reason": warning["warning"], "source_warning_index": index})
    # Only two explicit identities with effective work status can conflict.
    seen: dict[tuple[str, int], list[dict]] = {}
    for person in people:
        person_key = person.get("confirmed_person_id")
        if not isinstance(person_key, str):
            continue
        for item in person.get("daily", []):
            if _effective_status(item) != "work":
                continue
            key = (person_key, item["day"])
            for previous in seen.get(key, []):
                if previous["project"] != person.get("project"):
                    issues.append({
                        "record_id": person["record_id"], "project": person.get("project"),
                        "field": f"{data['month']}-{item['day']:02d}",
                        "reason": "同一已确认人员跨项目日期重复出勤",
                        "other_record_id": previous["record_id"], "other_project": previous["project"],
                    })
            seen.setdefault(key, []).append(person)
    return {"month": data["month"], "people_count": len(people), "stats": stats, "issues": issues}


def apply_file(data_path: Path, request_path: Path) -> dict:
    data = load_json(data_path)
    request = load_json(request_path)
    updated = apply_operations(data, request)
    atomic_json(data_path, updated)
    report = analyze(updated)
    changed_records = sorted({op["record_id"] for op in request["operations"] if op.get("record_id")})
    return {"ok": True, "updated_records": changed_records, "operation_count": len(request["operations"]), "month": report["month"], "issues": report["issues"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["apply", "check"])
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--request", type=Path, help="apply 命令的 JSON 操作请求")
    args = parser.parse_args()
    try:
        data_path = args.data.expanduser().resolve()
        if args.command == "apply":
            if args.request is None:
                raise ValueError("apply 需要 --request")
            result = apply_file(data_path, args.request.expanduser().resolve())
        else:
            result = {"ok": True, **analyze(load_json(data_path))}
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
