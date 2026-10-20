from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_unmatched_people_are_not_routed_to_creation():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    identity = (ROOT / "references" / "identity-matching.md").read_text(encoding="utf-8")
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    combined = skill + identity + payroll
    assert "create_payroll_person" not in combined
    assert "CreatePayrollPerson" not in combined
    assert "本次暂不纳入自动核算范围" in combined
    assert "不提示创建或补建人员" in payroll


def test_payroll_phases_require_separate_explicit_authorization():
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    for phase in ("考勤识别完成", "身份匹配完成", "考勤提交完成", "工资核算完成"):
        assert phase in payroll
    assert "submit_attendance" in payroll
    assert "calculate_payroll" in payroll
    assert "明确正式提交授权" in payroll
    assert "必须另行确认用户明确要求开始工资核算" in payroll
    assert "`valid` 不是 `true`" in payroll
    assert "不能描述为无写入的模拟试算" in payroll


def test_uncertain_write_results_require_readback_before_retry():
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    assert "get_attendance_submission" in payroll
    assert "get_payroll_calculation" in payroll
    assert "不得立即重试写操作" in payroll
    assert "不得另造操作 ID 绕过冲突" in payroll


def test_attendance_internal_outputs_are_kept_out_of_final_deliverables():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "`.attendance-work/`" in skill
    assert "`.attendance-pages/`" in skill
    assert "只声明 `考勤确认表.md` 和已成功核算并实际生成的正式工资表" in skill


def test_full_payroll_success_automatically_enters_export_and_declaration():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    assert "不再询问是否生成工资表" in skill
    assert "自动进入既有 `PAYROLL_EXPORT` 门禁" in payroll
    assert "不得在完整 SUCCESS 后另行询问是否导出" in payroll
    assert "不得再次调用 `calculate_payroll`" in payroll
    assert "工资核算已完成，但正式工资表导出失败" in payroll
    assert "Artifact `ok=true` 证明声明成功" in payroll
    assert "文件生成成功、交付未完成" in payroll


def test_attendance_chat_and_markdown_are_compact_while_source_keeps_daily_facts():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    attendance = (ROOT / "references" / "attendance-review.md").read_text(encoding="utf-8")

    assert "不得在聊天中复制完整人员表" in skill
    assert "用户明确询问特定人员或日期时" in attendance
    assert "不生成逐日章节或逐日矩阵" in attendance
    assert "逐日考勤明细" not in attendance
    assert "不支持删除考勤人员" in attendance
    assert "本次核算暂不纳入" in attendance
    assert "原始逐日状态、确认值、标记和来源仍完整保留" in attendance


def test_scope_exclusion_is_separate_from_identity_mapping_and_binds_current_message():
    identity = (ROOT / "references" / "identity-matching.md").read_text(encoding="utf-8")
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")
    gate = (ROOT / "scripts" / "workflow_gate.py").read_text(encoding="utf-8")

    assert "evidence.scope_exclusion_decisions" in payroll
    assert "confirmation_message_index" in payroll
    assert "身份映射 SHA" in payroll
    assert "scope_exclusion_decisions" in gate
    assert "不得把该记录改成 `matched`、`unmatched`" in identity
    assert "其他未解决的 `ambiguous` / `pending_confirmation` 仍会阻断" in identity
