package llm

import "context"

// Recorder 定义 LLM 调用记录的持久化和查询接口。
type Recorder interface {
	RecordCall(ctx context.Context, record *CallRecord) error
	ListCalls(ctx context.Context, orgID uint, offset, limit int, modelID *uint, provider, callerType *string, success *bool) ([]*CallRecord, int64, error)
	Shutdown(ctx context.Context) error
}
