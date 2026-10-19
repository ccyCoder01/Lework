#!/usr/bin/env python3
"""Export the current attendance work data as a concise project summary."""
from __future__ import annotations

import argparse
import calendar
import json
import os
import re
from pathlib import Path
import tempfile

from attendance_review import analyze, _person_stats
from attendance_store import load_json

HEADERS = ("序号", "姓名", "岗位", "实际出勤", "缺勤合计", "备注")


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _group_issues(issues: list[dict]) -> list[dict]:
    grouped = {}
    for issue in issues:
        key = (issue.get("record_id"), issue["reason"])
        item = grouped.setdefault(key, {"record_id": key[0], "reason": key[1], "days": set(), "dates": set(), "others": set(), "fields": set()})
        item["days"].update(issue.get("days", []))
        field = issue.get("field", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", field):
            item["dates"].add(field)
        elif field:
            item["fields"].add(field)
        if issue.get("other_record_id"):
            item["others"].add((issue["other_record_id"], issue.get("other_project", ""), issue.get("project", ""), field))
    result = []
    for item in grouped.values():
        detail = item["reason"]
        days = sorted(item["days"])
        dates = sorted(item["dates"])
        if days:
            detail += "：" + ", ".join(str(day) for day in days)
        if dates:
            shown = [f"{int(date[5:7])}月{int(date[8:10])}日" for date in dates[:5]]
            detail += f"（{'、'.join(shown)}{'等' if len(dates) > 5 else ''}共{len(dates)}日）"
        if item["fields"]:
            detail += f"（{ '、'.join(sorted(item['fields'])) }）"
        if item["others"]:
            refs = sorted(item["others"])
            detail += "（涉及记录/项目：" + "；".join(
                f"{record_id}/{other_project or '项目待确认'} ↔ {item['record_id']}/{project or '项目待确认'} {date}"
                for record_id, other_project, project, date in refs
            ) + "）"
        result.append({"record_id": item["record_id"], "reason": detail})
    return result


def render(data: dict) -> tuple[str, dict]:
    report = analyze(data)
    grouped_issues = _group_issues(report["issues"])
    people = data["people"]
    groups = {}
    for person in people:
        project = str(person.get("project", "")).strip() or "项目待确认"
        groups.setdefault(project, []).append(person)
    lines = [f"# {data['month']} 考勤确认表", "", f"- 考勤月份：{data['month']}"]
    sources = sorted({Path(str(person.get("source_document", ""))).name for person in people if person.get("source_document")})
    lines.append(f"- 来源文件：{'、'.join(_cell(s) for s in sources) if sources else '待确认'}")
    lines.append(f"- 识别人数：{len(people)}")
    lines.append(f"- 项目数量：{len(groups)}")
    lines.append("")
    for project, records in groups.items():
        lines.extend([f"## {_cell(project)}", "", "| 序号 | 姓名 | 岗位 | 实际出勤 | 缺勤合计 | 备注 |", "|---:|---|---|---:|---:|---|"])
        for number, person in enumerate(records, 1):
            stats, _ = _person_stats(person, calendar.monthrange(int(data["month"][:4]), int(data["month"][5:]))[1], data["month"])
            notes = [str(person.get("note", "")).strip()] if str(person.get("note", "")).strip() else []
            person_issues = [issue for issue in grouped_issues if issue.get("record_id") == person["record_id"]]
            notes.extend(issue["reason"] for issue in person_issues)
            cells = (number, person.get("name", "待确认"), person.get("position", ""), stats["actual_work_days"], stats["absence_days"], "；".join(notes))
            lines.append("| " + " | ".join(_cell(value) for value in cells) + " |")
        lines.append("")
    if grouped_issues:
        lines.extend(["## 待确认事项", ""])
        for issue in grouped_issues:
            person = next((p for p in people if p["record_id"] == issue.get("record_id")), {})
            label = person.get("name") or issue.get("record_id", "考勤数据")
            lines.append(f"- {_cell(label)}：{_cell(issue['reason'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", report


def export(data_path: Path, output_path: Path) -> dict:
    if output_path.name != "考勤确认表.md" or output_path.suffix.lower() != ".md":
        raise ValueError("输出文件名必须为 考勤确认表.md")
    data = load_json(data_path)
    content, report = render(data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_symlink():
        raise ValueError("拒绝覆盖符号链接产物路径")
    if output_path.exists():
        if not output_path.is_file():
            raise ValueError("产物目标不是普通文件")
        with output_path.open("r", encoding="utf-8") as existing:
            if not existing.readline().rstrip("\r\n").endswith("考勤确认表"):
                raise ValueError("目标文件不是已生成的考勤确认表，拒绝覆盖")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, prefix=".attendance-export-", suffix=".tmp", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_path, output_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    projects = {str(p.get("project", "")).strip() or "项目待确认" for p in data["people"]}
    return {"ok": True, "output": str(output_path.resolve()), "month": report["month"], "people_count": report["people_count"], "project_count": len(projects), "pending_count": len(report["issues"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = export(args.data.expanduser().resolve(), args.output.expanduser().absolute())
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
