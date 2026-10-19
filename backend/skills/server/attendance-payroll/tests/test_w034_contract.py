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
