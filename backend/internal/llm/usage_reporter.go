package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/ygpkg/yg-go/logs"
)

// UsageReporterConfig holds connection settings for reporting usage to the control plane.
type UsageReporterConfig struct {
	ServerAddr string
	OrgID      uint
	AuthToken  string
	HTTPClient *http.Client
}

// UsageReporter sends call records to the control plane via synchronous HTTP.
// Failures are logged but never block the caller.
type UsageReporter struct {
	cfg UsageReporterConfig
}

// NewUsageReporter creates a reporter with sensible HTTP client defaults.
func NewUsageReporter(cfg UsageReporterConfig) *UsageReporter {
	if cfg.HTTPClient == nil {
		cfg.HTTPClient = &http.Client{Timeout: 10 * time.Second}
	}
	return &UsageReporter{cfg: cfg}
}

// Report sends a single call record to the control plane endpoint.
// It is safe to call from goroutines. Nil receiver or empty config is a no-op.
func (r *UsageReporter) Report(ctx context.Context, record *CallRecord) {
	if r == nil || record == nil || r.cfg.ServerAddr == "" || r.cfg.OrgID == 0 {
		return
	}

	payload := usageReportPayload{
		OrgID:           r.cfg.OrgID,
		ModelID:         record.ModelID,
		Provider:        record.Provider,
		ModelName:       record.ModelName,
		ModelProvider:   record.ModelProvider,
		EntryProtocol:   record.EntryProtocol,
		IsStream:        record.IsStream,
		InputTokens:     record.InputTokens,
		OutputTokens:    record.OutputTokens,
		TotalTokens:     record.TotalTokens,
		LatencyMS:       record.LatencyMS,
		PromptTokens:    record.PromptTokens,
		CacheHitTokens:  record.CacheHitTokens,
		CacheMissTokens: record.CacheMissTokens,
		StatusCode:      record.StatusCode,
		Success:         record.Success,
		Status:          record.Status,
		Message:         record.Message,
		CallerType:      record.CallerType,
		ReqID:           record.ReqID,
		TraceID:         record.TraceID,
		RetryTimes:      record.RetryTimes,
		InputLen:        record.InputLen,
		OutputLen:       record.OutputLen,
		InputTruncated:  record.InputTruncated,
		OutputTruncated: record.OutputTruncated,
		ClientIP:        record.ClientIP,
		ProjectID:       record.ProjectID,
		SessionID:       record.SessionID,
		MessageID:       record.MessageID,
		AssistantID:     record.AssistantID,
		Uin:             record.Uin,
		Input:           record.Input,
		Output:          record.Output,
		StartedAt:       record.StartedAt,
		FinishedAt:      record.FinishedAt,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		logs.WarnContextf(ctx, "usage reporter: marshal failed: %v", err)
		return
	}

	url := normalizeServerURL(r.cfg.ServerAddr) + "/v1/llm/usage"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		logs.WarnContextf(ctx, "usage reporter: create request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if r.cfg.AuthToken != "" {
		req.Header.Set("Authorization", "Bearer "+r.cfg.AuthToken)
	}

	resp, err := r.cfg.HTTPClient.Do(req)
	if err != nil {
		logs.WarnContextf(ctx, "usage reporter: send: %v", err)
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		logs.WarnContextf(ctx, "usage reporter: server returned %d", resp.StatusCode)
	}
}

// usageReportPayload is the JSON body sent to the control plane.
type usageReportPayload struct {
	OrgID           uint      `json:"org_id"`
	ModelID         uint      `json:"model_id"`
	Provider        string    `json:"provider"`
	ModelName       string    `json:"model_name"`
	ModelProvider   string    `json:"model_provider"`
	EntryProtocol   string    `json:"entry_protocol"`
	IsStream        bool      `json:"is_stream"`
	InputTokens     int       `json:"input_tokens"`
	OutputTokens    int       `json:"output_tokens"`
	TotalTokens     int       `json:"total_tokens"`
	LatencyMS       int64     `json:"latency_ms"`
	PromptTokens    int64     `json:"prompt_tokens"`
	CacheHitTokens  int64     `json:"cache_hit_tokens"`
	CacheMissTokens int64     `json:"cache_miss_tokens"`
	StatusCode      int       `json:"status_code"`
	Success         bool      `json:"success"`
	Status          string    `json:"status"`
	Message         string    `json:"message"`
	CallerType      string    `json:"caller_type"`
	ReqID           string    `json:"req_id"`
	TraceID         string    `json:"trace_id"`
	RetryTimes      int64     `json:"retry_times"`
	InputLen        int       `json:"input_len"`
	OutputLen       int       `json:"output_len"`
	InputTruncated  bool      `json:"input_truncated"`
	OutputTruncated bool      `json:"output_truncated"`
	ClientIP        string    `json:"client_ip"`
	ProjectID       uint      `json:"project_id"`
	SessionID       uint      `json:"session_id"`
	MessageID       uint      `json:"message_id"`
	AssistantID     uint      `json:"assistant_id"`
	Uin             uint      `json:"uin"`
	Input           string    `json:"input"`
	Output          string    `json:"output"`
	StartedAt       time.Time `json:"started_at"`
	FinishedAt      time.Time `json:"finished_at"`
}

// normalizeServerURL ensures the server address has an http:// prefix.
func normalizeServerURL(serverAddr string) string {
	serverAddr = strings.TrimSpace(serverAddr)
	if serverAddr == "" {
		return ""
	}
	if strings.HasPrefix(serverAddr, "http://") || strings.HasPrefix(serverAddr, "https://") {
		return strings.TrimRight(serverAddr, "/")
	}
	return "http://" + strings.TrimRight(serverAddr, "/")
}
