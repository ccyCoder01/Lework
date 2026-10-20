# 考勤 PDF 固定视图识别（W02.4）

## 识别边界

预处理脚本在一次调用中以 300 DPI 渲染每个物理页，并进行一次有界的整体倾斜评估；随后为每页生成：

- 一张整页布局概览，用于识别标题、月份、列顺序、表格行和跨页续表关系。概览只做布局观察，不录入业务事实。
- 一至三张固定全宽人员行带，供识别姓名、岗位、每日标记、印刷实际出勤及备注。每页概览加数据视图最多四张。

整体纠偏只搜索约 `-2.0°..+2.0°`，步长 `0.1°`；仅在检测角度至少 `0.35°`、水平投影分数相对提升至少 `1%` 且最佳角度未触及搜索边界时执行旋转。旋转采用扩边，避免裁掉页面边缘。条件不足或处理异常时保留原图并在 manifest `deskew` 元数据中说明原因。该算法只处理整页轻微旋转，不能修复透视、弯曲纸面或局部倾斜；若页面仍不可读，记录质量限制并待核。预处理版本为 3；旧版本缓存不得与新视图混用，应在新任务目录运行。

清单 `recognition_role` 使用 `layout_only_no_business_fact_extraction` 标记概览，使用 `primary_rows_by_printed_row_index` 标记人员行数据视图。

行带根据确定性墨迹范围分为互不重叠的 `core_region`，并在图像边缘加入固定重叠，保证靠近分区边界的整行仍有足够上下文。Agent 只录入人员行中心落在该视图核心区域的行；重叠部分不重复录入。每个视图最多读取一次。

固定视图是在预处理阶段一次生成的。Agent 不得自行裁图、放大、拼接、增强、标注或重渲染，不调用 OCR、视觉子代理，也不得因模糊内容重读概览或分区。视图区域不确定、行高不足或字段冲突时，记录待核警告并停止。不得用姓名合并人员。

整页概览只服务布局；人员值只能从该页 `row_partition` 视图录入。清单的 `expected_row_range` 只有在来源证据可确定时才填写；脚本无法可靠推断原表行号时为 `null`，不得伪造。Agent 将原表印刷序号作为 `row_index`；同一页同一序号重复时 `save-page` 拒绝保存，要求基于已读视图修正。不同页或不同项目的同名人员保持独立。

续表页若未重复打印日期列标题，只能沿用本 PDF 首个带有日期标题的布局概览映射列位置；不得把上一页人员数据带入续页。人员行按当前页可见的印刷序号绑定。

## 执行命令

```sh
python3 scripts/pdf_prepare.py --input <考勤.pdf> [其他.pdf ...] --workdir <工作目录>
python3 scripts/attendance_store.py save-page --workdir <工作目录> --result <当前页识别.json>
python3 scripts/attendance_store.py status --workdir <工作目录>
python3 scripts/attendance_store.py assemble --workdir <工作目录>
python3 scripts/attendance_review.py check --data <工作目录>/attendance.json
python3 scripts/attendance_diagnostics.py --workdir <工作目录>
```

同一任务若已有清单，`pdf_prepare.py` 校验来源后只复用既有视图，不重新渲染。换了 PDF 内容或路径时必须使用新任务目录，不能覆盖页面缓存。

## 页级 JSON

整页所有固定视图识别完成后，只生成一份页级 JSON，完成后立即调用 `save-page`：
下面只展示几天字段的格式；实际 JSON 必须逐日列齐全月，只有明确列入 `missing_days` 的日期可以缺少。

```json
{
  "schema_version": 1,
  "document_id": "doc-1",
  "page": 1,
  "month": "2026-06",
  "project": "项目名称；无法确认时为空字符串",
  "people": [
    {
      "row_index": 1,
      "source_view_id": "doc-1-p001-rows-01",
      "name": "张三",
      "position": "施工员",
      "printed_work_days": "25",
      "row_binding_status": "VERIFIED",
      "printed_work_days_row_index": 1,
      "note_row_index": null,
      "daily": [
        {"day": 1, "raw_mark": "8", "status": "work"},
        {"day": 2, "raw_mark": "休", "status": "rest"},
        {"day": 3, "raw_mark": "?", "status": "unknown"}
      ],
      "note": ""
    }
  ],
  "warnings": [],
  "quality_warnings": []
}
```

`row_index` 是表格印刷行号，不是数组位置。每条有确定行号的记录还须填写 `source_view_id`，引用本页清单中的 `row_partition`；若清单给出 `expected_row_range`，行号必须在该范围内。无法绑定时使用 `row_index: null`、`row_binding_status: "UNRESOLVED"`，并填写 `row_binding_warning`。`printed_work_days_row_index` 必须等于该人的 `row_index`；非空备注须通过 `note_row_index` 绑定到同一行。任一字段不能可靠绑定时，对应索引置为 `null` 并将行绑定标记为待核，不得把相邻行姓名、岗位、每日格、印刷汇总或备注拼到同一人。

每天必须有一条 `daily` 记录；看不清时保留原始可见符号（不清晰写 `?`）并用 `status: "unknown"`。确实无法列出日期时，将日期逐一放入 `missing_days` 并写警告。空格只有在原件明确为空时才写 `raw_mark: ""`、`status: "blank"`。已确认符号例如 `8/√=work`、`休=rest`、`换=comp_leave`；其他含义不确定则用 `unknown`。

`printed_work_days` 与逐日观察互相独立保存。保存校验若发现两者计数不同，会在 `quality_warnings` 增加差异说明，不会改动任一事实。逐日出勤和印刷汇总一致不代表视觉识别无误；仍须检查行序、人员身份、日期列及未知状态。核对表的实际出勤优先采用明确的 `confirmed_work_days`；否则仅在 `row_binding_status=VERIFIED` 且 `printed_work_days_row_index=row_index` 时采用可解析的印刷值。逐日出勤数用于差异诊断，不覆盖可靠绑定的印刷值；印刷行绑定不可靠时显示待确认。`quality_warnings` 和原始 `warnings` 都会进入后续核对数据。

识别结果及用户确认不得覆盖原 PDF 或原始 `raw_mark/status`。`attendance_store.py assemble` 只在所有页级 JSON 有效时生成工作数据；历史 JSON 没有视图字段时继续按旧 W01 结构读取。

## 诊断与能力边界

`attendance_diagnostics.py` 只读取清单、视图元数据、页级 JSON、`attendance.json` 和脚本运行记录；不读取 PDF 或图片。它统计每页视图、预计行范围、重复/缺失行号、行绑定异常、未知状态和印刷/逐日差异。预处理耗时来自脚本单调时钟；模型推理耗时和 Agent 实际图片调用次数没有可靠来源时为 `null`。

Skill 和页 JSON 校验可以约束正常路径，但 Runtime 未强制视图读取次数。拥有任意工具或 Shell 权限的 Agent 仍可能绕过规定；不能把本方案描述为 Runtime 级隔离。
