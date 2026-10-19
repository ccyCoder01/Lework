# 人员身份匹配

本阶段只将当前 `attendance.json` 的人员记录与 Payroll 已有人员档案关联，不更改考勤、不创建或修改 Payroll 人员，也不提交考勤或计算工资。

## 只读资料来源

1. 调用 Payroll MCP `list_roster` 获取当前有效花名册。其记录含 `roster_id`、`name`、`project_name`、`company_name`、`employee_type`、`position` 和 `gender`。
2. 用脚本生成绑定当前考勤和别名文件的候选请求：

   ```sh
   python3 scripts/person_matches.py candidate-request \
     --attendance <workdir>/attendance.json \
     --output <workdir>/candidate-query.json
   ```

   将文件中的 `records` 数组原样传给 `resolve_payroll_person_candidates`，并把实际发送的整个请求体原样保存为 `candidate-query.json`。每批最多 100 条，`client_ref` 必须唯一。脚本会对显式项目别名进行精确规范化，并省略 `position` 查询字段，避免岗位变更造成候选过滤或冲突；岗位仍作为可解释的辅助信息检查。
3. 候选响应按 `client_ref` 返回 `candidates`；候选含 `payroll_person_id`、`roster_id`、身份字段、`matched_fields`、`conflicting_fields`、`match_status`、`review_reasons` 及证据。该工具只返回候选，不会替用户确认或写入 Payroll。

把工具返回的 JSON 响应保存为临时输入文件，调用：

```sh
python3 scripts/person_matches.py build \
  --attendance <workdir>/attendance.json \
  --roster <workdir>/list-roster.json \
  --candidates <workdir>/candidate-response.json \
  --query <workdir>/candidate-query.json \
  --output <workdir>/person-matches.json
```

`person-matches.json` 仅保存当前任务的关联状态、候选摘要、匹配依据及输入摘要，不复制完整 Payroll 档案。生成结果不能替代考勤核对表，也不应声明为正式 Artifact。

## 状态及确定性规则

- `matched`：自动匹配时，姓名、项目、公司、用工性质均有完整来源事实，与候选和唯一当前有效花名册记录精确一致，没有关键冲突，且没有其他与来源事实相容的合理候选。岗位是软辅助字段，不要求必须相同，也不单独阻止自动匹配；差异作为提示保留。仅表示身份关系明确。
- `ambiguous`：有多个对已知事实均无冲突的候选。
- `unmatched`：没有候选。
- `pending_confirmation`：候选存在但来源字段不足、候选存在冲突、候选没有当前有效花名册记录，或无法确认唯一关联。

姓名、公司、用工性质只做去除首尾空格后的精确比较，不使用姓名相似度、拼音或缺失值补全。项目只允许 [project-aliases.json](project-aliases.json) 中明确列出的精确别名映射；原考勤项目名继续保留在来源事实中，映射配置摘要绑定到 `person-matches.json`。对瀚阅府，`瀚阅府西苑项目` 与 `瀚阅府` 规范到 `瀚阅府`。不能用包含关系、模糊匹配或任意同义词扩展别名。`attendance.json` 当前通常不含公司和用工性质，因此即使姓名和项目相同，也不能自动绑定 Payroll ID；不同项目、公司或用工性质的同名候选应分别展示。

Payroll 当前候选响应中的 `match_status=REQUIRES_REVIEW` 是候选工具的常规状态，不单独代表候选无效。`evidence_level` 的已实现值为 `NAME_ONLY`、`SUPPORTING`、`CONFLICTING`；`project_match_status` 的已实现值包括 `PROJECT_MATCHED`、`PROJECT_UNKNOWN`、`PROJECT_CONFLICT`、`NOT_REQUESTED`。`review_reasons` 中的 `*_EVIDENCE_MISSING` 表示查询所需证据不足，不能自动匹配；`*_EVIDENCE_CONFLICT` 和 `MULTIPLE_ROSTER_IDENTITIES` 表示必须阻止普通确认。实际规则以脚本对字段和当前 `list_roster` 响应的交叉校验为准，未知枚举或结构一律保守拒绝。

### 自动匹配与普通确认

- 自动 `matched` 要求考勤来源完整提供姓名、项目、公司、用工性质和岗位；候选与这些事实精确一致；候选具有唯一、当前有效且身份字段一致的花名册关联；没有关键冲突；并且不存在其他与已知来源事实相容的候选。任何来源字段缺失、多个合理候选或无法排除的歧义都不能自动绑定。
- 普通人工确认可以补足考勤来源缺失的公司、用工性质等字段，但只限于：候选姓名与考勤姓名一致，候选和 Payroll 身份证据内部一致，候选关联当前 `list_roster` 中有效且核心身份字段一致的唯一花名册记录，并且没有关键冲突或多重花名册身份。岗位差异及 `POSITION_EVIDENCE_CONFLICT` 是软提示，不单独阻断确认；`*_EVIDENCE_MISSING` 本身也不是冲突。用户须先看到候选的实际项目、公司、用工性质、岗位、人员 ID 和有效性，再明确指定该候选。
- 普通确认必须拒绝姓名、项目、公司或用工性质冲突，`evidence_level=CONFLICTING` 中的核心字段冲突、项目状态无法由明确别名解释、多个身份来源不一致、花名册缺失/失效/不一致，以及 `MULTIPLE_ROSTER_IDENTITIES`。本 Skill 没有强制覆盖路径；即使用户要求绕过，也不能直接改写身份映射。
- Payroll 可能在未配置服务端别名时仍返回项目冲突。脚本只在候选、花名册和身份证据中出现的所有非空项目名都按显式映射归一为同一个来源项目时，才把该项目冲突视为可解释；真实的多项目证据冲突仍阻断。岗位字段不参与该别名判断。
- 若响应出现无法识别的关键状态、无法核验候选身份或候选证据与当前花名册不一致，保留待确认并重新获取当前只读资料或报告阻塞，不猜测。

## 用户确认

用户自然语言明确指定人员关系后，Agent 仅将其转换成下列结构化批次；每项必须引用 `record_id` 和候选响应中的 `payroll_person_id`，并附简短的用户确认依据：

```json
{
  "confirmations": [
    {
      "record_id": "doc-1-p1-r4",
      "payroll_person_id": 123,
      "user_confirmation": "用户明确确认该考勤记录对应此人员"
    }
  ]
}
```

```sh
python3 scripts/person_matches.py confirm \
  --attendance <workdir>/attendance.json \
  --roster <workdir>/list-roster.json \
  --candidates <workdir>/candidate-response.json \
  --matches <workdir>/person-matches.json \
  --request <workdir>/confirmations.json \
  --query <workdir>/candidate-query.json
```

脚本先整体核对考勤、花名册、候选响应、候选查询请求、别名配置摘要及映射中的候选快照，再复用与自动匹配相同的核心候选安全校验，验证所有记录、候选 ID 和重复目标，最后原子写入；任一错误都不产生部分修改。确认操作必须使用与构建映射时相同的查询请求和只读 Payroll 响应。用户确认只确认身份对应关系，不批准考勤，不授权进入工资阶段。若候选不在当前响应中，重新查询并向用户说明候选变化，不得手工填入任意 ID。考勤来源或别名配置变化后必须重新构建候选。

确认前向用户展示足以辨别身份的候选信息：Payroll 人员 ID、姓名、项目、公司、用工性质、岗位、当前花名册有效性，以及任何冲突/缺失证据。不能只展示姓名并询问“是否匹配”。用户的回复必须能唯一对应某条考勤 `record_id` 和一个候选 ID；含糊回复不得转换为确认。批量确认先校验全部项目，任何一项不安全则整批拒绝且不写入文件。

W03 仅允许 `list_roster` 和 `resolve_payroll_person_candidates` 两项只读查询。禁止调用 `submit_attendance`、`calculate_payroll` 或任何 Payroll 写接口。身份匹配成功不代表考勤审批，也不代表用户授权工资计算。

完成后向用户说明已明确对应、待确认和未找到的人数，以及尚不能进入后续阶段的记录。后续工资阶段仍需用户单独明确授权。
