package prompts

func init() {
	Register(KeyFeedbackSummarize, `你是一位中文产品反馈整理助手。请阅读用户反馈，生成简洁标题，并用自己的话概括问题核心。

反馈类型：{feedback_type}
用户原文：
{content}

输出要求：
- 只输出一个合法 JSON 对象，不要 Markdown，不要代码块，不要解释。
- JSON 格式：{"title":"...","understanding":"..."}
- title：6 到 20 个中文字符，概括反馈主题；不要包含用户名、手机号、版本号；不要加“【BUG】”等类型前缀。
- understanding：1 到 3 句中文，说明你对问题的理解、可能影响或建议关注点；不要重复原文，不要编造用户未提及的事实。
- 两个字段都必须非空。

JSON：`)
}
