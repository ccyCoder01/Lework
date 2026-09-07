package llm

import "context"

// Caller 定义统一的 LLM 调用接口，支持非流式和流式两种模式。
type Caller interface {
	Call(ctx context.Context, orgID uint, req *CallRequest) (*CallResult, error)
	Stream(ctx context.Context, orgID uint, req *CallRequest, sink StreamSink) (*CallResult, error)

	// CallRaw 使用已解析的 ModelConfig 和已序列化的请求体做非流式调用。
	// 调用方负责构造上游协议的请求体，Caller 负责 HTTP 调用、usage 解析和计费记录。
	CallRaw(ctx context.Context, orgID uint, cfg *ModelConfig, body []byte) (*CallResult, error)

	// StreamRaw 使用已解析的 ModelConfig 和已序列化的请求体做流式调用。
	// 调用方通过 rawChunkSink 接收上游 SSE 原始 chunk，自行包装 SSE 格式。
	// Caller 负责 HTTP 调用、usage 解析和计费记录。
	StreamRaw(ctx context.Context, orgID uint, cfg *ModelConfig, body []byte, rawChunkSink RawChunkSink) (*CallResult, error)
}

// RawChunkSink 定义流式原始 chunk 回调接口，供调用方接收上游 SSE 原始数据。
type RawChunkSink interface {
	EmitRawChunk(ctx context.Context, chunk []byte) error
}
