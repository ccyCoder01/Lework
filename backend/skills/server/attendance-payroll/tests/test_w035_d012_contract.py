from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payroll_task_identity_is_path_derived_not_user_supplied_or_authority():
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "task_context.py").read_text(encoding="utf-8")

    assert "<repo>/.leros/tasks/<task_id>/turns/<request_id>/tmp" in payroll
    assert "scripts/task_context.py discover" in payroll
    assert "is_authorization_proof=false" in payroll
    assert 'source": "runtime_turn_tmp_path"' in script
    assert '"confidence": "context_derived"' in script
    assert "不要询问用户填写 Task ID 或 Batch ID" in payroll
    assert "路径不完整、仓库不匹配、结构错误、符号链接或 ID 格式错误时，停止相关流程" in payroll
    assert "发现 Task ID 不构成授权" in skill
    assert "不向用户索取 Task ID 或 Batch ID" in skill


def test_batch_ids_are_stable_and_scope_or_local_state_is_not_authority():
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    assert "`batch_id` 固定为 `<task_id>-<YYYY-MM>`" in payroll
    assert "绝不追加人数、随机数或时间后缀生成新批次" in payroll
    assert "它不是授权、Payroll 回执或服务端事实" in payroll
    assert "不保存本地批次状态" in payroll
    assert "用户授权必须仍来自当前对话中对确切月份、考勤版本和完整人员范围的明确表达" in payroll


def test_payroll_scope_changes_and_unknown_cross_batch_impact_fail_closed():
    payroll = (ROOT / "references" / "payroll-processing.md").read_text(encoding="utf-8")

    assert "不提供按月份和人员范围查询其他批次的完整能力" in payroll
    assert "不得通过新 Batch ID 或 Operation ID 绕过冲突" in payroll
    assert "不得自行把 39 人改成 31 人" in payroll
    assert "Precheck 阻塞不授权自动排除人员" in payroll
    assert "若不能可靠核实其他批次及已计算结果的影响，停止正式写入" in payroll
    assert "operation_id` 固定为 `submit:<batch_id>" in payroll
    assert "operation_id` 为 `calculate:<batch_id>" in payroll


def test_attendance_review_is_declared_final_in_one_explicit_call():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert '"path": "<导出结果中的绝对路径>"' in skill
    assert '"title": "<例如：2026年6月考勤确认表>"' in skill
    assert '"mime_type": "text/markdown"' in skill
    assert '"artifact_type": "file"' in skill
    assert '"is_final": true' in skill
    assert "不得先声明 `is_final=false` 再依赖 Git Diff 兜底" in skill
    assert "只有响应 `ok=true` 才表示声明成功" in skill
