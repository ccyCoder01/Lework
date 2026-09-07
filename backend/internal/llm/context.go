package llm

import "context"

// CtxKey 是 LLM 调用 context key 的类型。
type CtxKey string

// LLM 调用相关的 context key，用于从 ctx 中传递/提取业务 ID。
const (
	CtxProjectID   CtxKey = "llm_project_id"
	CtxSessionID   CtxKey = "llm_session_id"
	CtxMessageID   CtxKey = "llm_message_id"
	CtxAssistantID CtxKey = "llm_assistant_id"
	CtxUin         CtxKey = "llm_uin"
	CtxTraceID     CtxKey = "llm_trace_id"
	CtxClientIP    CtxKey = "llm_client_ip"
	CtxCallerType  CtxKey = "llm_caller_type"
	CtxReqID       CtxKey = "llm_req_id"
	CtxRunID       CtxKey = "llm_run_id"
)

// WithCtxUint 将业务 ID 注入 context，val 为 0 时不做注入。
func WithCtxUint(ctx context.Context, key CtxKey, val uint) context.Context {
	if val == 0 {
		return ctx
	}
	return context.WithValue(ctx, key, val)
}

// GetCtxUint 从 context 中提取业务 ID，未设置时返回 0。
func GetCtxUint(ctx context.Context, key CtxKey) uint {
	if ctx == nil {
		return 0
	}
	v, _ := ctx.Value(key).(uint)
	return v
}

// WithCtxString 将字符串值注入 context，值为空时不注入。
func WithCtxString(ctx context.Context, key CtxKey, val string) context.Context {
	if val == "" {
		return ctx
	}
	return context.WithValue(ctx, key, val)
}

// GetCtxString 从 context 中提取字符串值，未设置时返回空。
func GetCtxString(ctx context.Context, key CtxKey) string {
	if ctx == nil {
		return ""
	}
	v, _ := ctx.Value(key).(string)
	return v
}
