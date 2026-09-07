package prompts

func init() {
	Register(KeyWorkShortTitle, `你是一位中文产品标题助手。请根据下面的对话内容，为项目、任务和会话生成极短标题。

上下文：
- 用户首条消息：
{user_message}
- 助手首轮回复（可能为空）：
{assistant_message}

输出要求：
- 只输出一个合法 JSON 对象，不要 Markdown，不要代码块，不要解释。
- JSON 格式：{"project_title":"...","task_title":"...","session_title":"..."}
- project_title、task_title、session_title 三个字段都必须输出非空标题。
- 你只负责生成标题候选，不要判断业务上是否应该更新项目标题。
- 中文优先，尽量 6 到 12 个中文字符，最长不超过 20 个中文字符。
- 保留核心对象和动作，例如“季度经营分析”“登录异常排查”“投标文件整理”。
- 避免“帮我”“请帮我”“任务”“需求”“分析一下”“处理一下”等泛化词。
- 不使用句号、问号、冒号、引号等标点。

JSON：`)
}
