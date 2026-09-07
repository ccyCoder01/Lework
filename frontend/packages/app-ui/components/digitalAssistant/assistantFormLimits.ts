// 中文注释：创建与编辑入口共享同一套长度限制，避免同一字段在不同弹窗中的校验标准不一致。
export const ASSISTANT_FORM_LIMITS = {
	name: 20,
	roleName: 30,
	description: 200,
	systemPrompt: 2000,
} as const;
