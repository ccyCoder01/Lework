# 考勤核对与统计约定（W02）

## 数据边界

- `attendance.json` 是唯一可修改的工作数据；`.attendance-pages/**/page-*.json` 是只读识别快照，禁止修改。
- 受控更正只更新当前工作数据，不覆盖 PDF 或页级快照。更正后重新核对并导出 Review；当前事实版本由工作文件 SHA-256 表示。本流程没有独立 Generation 计数器，不能把调用者自填的版本标签当作版本证明。
- 更正后的新 Review 只能表示本地考勤事实已修订。若原 Task/月已有正式 Payroll 提交或核算回执，不能把本地更正表述为 Payroll 已更新；按工资处理流程的回执门禁停止正式写入。
- 每条人员记录由 W01 生成的 `record_id` 唯一定位。姓名不作为主键；同名记录不得合并。
- 原始每日标记保存在 `daily[].raw_mark`，原始解释状态保存在 `daily[].status`，二者均不可被用户更正覆盖。更正另存 `user_confirmed_mark`（可选）和 `user_confirmed_status`，统计优先采用用户确认状态；修改事实不会改写 PDF 来源事实。
- `printed_work_days` 保留 PDF 印刷值。用户确认的实际出勤单独存为 `confirmed_work_days`，不覆盖印刷值或原始逐日事实。
- W01 页级识别 `warnings` 在组装时保留为 `source_warnings`，原文不可修改。核对和导出展示尚未解决的警告；自由文本不做关键词匹配，也不会因相关字段看似已更正而自动消失。
- 用户明确表示某条来源警告已核实时，可用 `{"op":"resolve_source_warning","warning_index":0,"confirm_resolved":true}` 将该条标记为已处理。索引对应 `source_warnings` 的原始顺序；只新增绑定该条原始内容的 `resolved_source_warnings` 确认，不改原始警告。未明确确认时保持待核，其他警告和当前数据异常继续独立显示。若原始警告内容与确认绑定不一致，校验失败，不会隐藏警告。
- 可使用 `confirmed_person_id` 识别已确认的同一人员。仅同名、同岗位或相同日期不足以证明身份相同。

## 汇总口径

- 未更正的原始状态只有在与 W01 已记录的符号规则相符时才参与统计：`8`/`√`=出勤、`休`=休息、`换`=换休、`事`=事假、`病`=病假、`旷`=旷工、`产`=产假、空格=空白。其他原始符号与状态组合一律待确认，不因模型填入了标准状态就自动计数。
- `work` 计入逐日观察出勤；`rest`、`comp_leave` 不计入缺勤。
- 已确认的 `annual_leave`、`personal_leave`、`sick_leave`、`absent`、`maternity_leave`、`other_paid_leave` 是非出勤状态，按逐日记录合计显示在“缺勤合计”。原始符号没有明确映射时，须由用户确认后才按其更正状态统计。如项目对该字段有不同业务口径，应保留为待确认，不能静默套用。
- `unknown`、`blank`、缺失日期、`transfer`、`departed` 均不能被当作出勤或缺勤。出现这些情况时，相应合计显示“待确认”。调离或离职后的日期不能直接计作缺勤。
- 有效日期必须覆盖当月日历日且每天只出现一次。缺日、重复日、未知状态和无效状态均进入待确认事项。
- `printed_work_days` 可解析为当月范围内整数，且 `row_binding_status=VERIFIED`、`printed_work_days_row_index=row_index` 时，视为可靠绑定的印刷来源值；实际出勤优先级为用户确认的 `confirmed_work_days`，其次是可靠印刷值，否则为“待确认”。逐日 `work` 数只用于差异诊断；与可靠印刷值不一致时保留双方数值并提示核实，不自动覆盖印刷值或每日状态。行绑定无法确认时，不能把印刷值算作该人员实际出勤。
- 来源文档、页码和 `row_index` 同时存在时，同一来源页的行号必须唯一；印刷汇总和非空备注分别以对应的 `printed_work_days_row_index`、`note_row_index` 绑定到同一人员行。发现行号重复或字段行号不一致时，检查失败，不导出错误关联。
- 不使用“日历天数减实际出勤”推算缺勤。
- 跨项目重复出勤只在记录具有相同非空 `confirmed_person_id`，且双方同日有效状态均为 `work` 时报告。每日有效状态优先采用 `user_confirmed_status`；否则仅采用与固定原始符号规则相符的 `status`。休息、换休、未知、调离及离职不作为重复出勤。结果保留双方记录、项目和日期，不合并记录或推定项目归属；同名人员保持分开。
- 外部或历史工作数据中的确认字段必须通过统一文档校验：`confirmed_work_days` 是当月范围内的整数（不接受布尔值）；存在的 `confirmed_person_id` 必须是无首尾空格的非空字符串；每日确认状态必须属于状态枚举；确认标记必须为字符串。`check`、`apply` 和导出使用同一校验，不接受静默转换。
- 空项目归属显示“项目待确认”，不得从 PDF 文件名推断。

## 修改请求

通过 JSON 请求调用脚本，不手工编辑大型 JSON。请求最外层为 `{"operations": [...]}`，每项必须含稳定 `record_id`。

```json
{
  "operations": [
    {"op": "set_daily_status", "record_id": "doc-1-p1-r1", "day": 3, "status": "rest", "confirmed_mark": "用户确认休息"},
    {"op": "set_actual_work_days", "record_id": "doc-1-p1-r1", "value": 25},
    {"op": "resolve_source_warning", "warning_index": 0, "confirm_resolved": true}
  ]
}
```

允许的 `status` 与 W01 `attendance_store.py` 相同：`work`、`rest`、`comp_leave`、`annual_leave`、`personal_leave`、`sick_leave`、`absent`、`maternity_leave`、`other_paid_leave`、`transfer`、`departed`、`unknown`、`blank`。这只是标准字段取值，不代表可从原始符号自动映射；映射须来自用户确认或来源明确的项目规则。用户更正写入独立字段，不覆盖原始 `raw_mark` / `status`。

执行方式：

```sh
python3 scripts/attendance_review.py apply --data <工作目录>/attendance.json --request <请求.json>
python3 scripts/attendance_review.py check --data <工作目录>/attendance.json
```

批量操作先整体校验，任一目标、日期、状态或重复目标无效则全部拒绝。成功时只原子替换 `attendance.json`；不改识别快照，不提供撤销栈或修改历史。响应 JSON 包含 `ok`、受影响记录、操作数和当前异常列表。错误通过非零退出码及 `{"ok":false,"error":"..."}` 返回。

## 导出

```sh
python3 scripts/attendance_export.py --data <工作目录>/attendance.json --output <当前项目仓库>/考勤确认表.md
```

脚本只允许目标文件名 `考勤确认表.md`，可在同一任务内重生成该文件。正式 Markdown 只输出按人员汇总的固定六列表格：序号、姓名、岗位、实际出勤、缺勤合计、备注；不生成逐日章节或逐日矩阵。待确认事项、缺日、未知状态、印刷值冲突和来源警告仍须保留在汇总备注或待确认事项中。原始逐日状态、确认值、标记和来源仍完整保留在 PDF/页级 JSON/`attendance.json`，本次展示精简不改变更正、统计或来源核验功能。同名人员由不同 `record_id` 保持为独立汇总行。响应 JSON 给出绝对路径、月份、人数、项目数及待确认事项数。

Agent 在提出更正或范围处理方案前，先按本文件中的 CLI 示例核对 `attendance_review.py` 实际支持的操作。当前仅支持 `set_daily_status`、`set_actual_work_days` 和经明确确认的 `resolve_source_warning`；不支持删除考勤人员。身份匹配与“本次核算暂不纳入”是独立决定，不能通过修改考勤事实实现排除，也不能因本次排除删除原始人员记录。

Agent 的正常聊天回复只简短说明月份、项目、识别人数/页数（有可靠数据时）、核对结果、待确认事项摘要及文件交付状态，不重复整表或逐日明细。用户明确询问特定人员或日期时，只展示对应信息。

该文件生成不等于产物声明成功，也不证明 UI 卡片已显示。由 Agent 按主 Skill 调用 `artifact_declare` 并核验成功响应。
