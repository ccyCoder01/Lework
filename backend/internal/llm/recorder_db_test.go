package llm

import (
	"context"
	"testing"
	"time"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"github.com/insmtx/Leros/backend/types"
)

func setupRecorderDB(t *testing.T) *RecorderDb {
	t.Helper()
	database, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("failed to open test database: %v", err)
	}
	if err := database.AutoMigrate(&types.LLMHistory{}); err != nil {
		t.Fatalf("failed to migrate: %v", err)
	}
	return NewRecorder(database)
}

func TestRecorderRecordCallAndListCalls(t *testing.T) {
	recorder := setupRecorderDB(t)
	ctx := context.Background()
	now := time.Now().Truncate(time.Second)

	record := &CallRecord{
		OrgID:         testOrgID,
		ModelID:       10,
		Provider:      "openai",
		ModelName:     "gpt-4o-mini",
		EntryProtocol: "eino_chat",
		IsStream:      false,
		InputTokens:   100,
		OutputTokens:  50,
		TotalTokens:   150,
		LatencyMS:     2000,
		StatusCode:    200,
		Success:       true,
		Status:        "success",
		CallerType:    "worker",
		ReqID:         "task-123",
		ProjectID:     1,
		SessionID:     2,
		MessageID:     3,
		AssistantID:   4,
		Uin:           5,
		StartedAt:     now,
		FinishedAt:    now.Add(2 * time.Second),
	}

	if err := recorder.RecordCall(ctx, record); err != nil {
		t.Fatalf("RecordCall failed: %v", err)
	}

	time.Sleep(50 * time.Millisecond)

	records, total, err := recorder.ListCalls(ctx, testOrgID, 0, 50, nil, nil, nil, nil)
	if err != nil {
		t.Fatalf("ListCalls failed: %v", err)
	}
	if total != 1 {
		t.Fatalf("expected total=1, got %d", total)
	}
	if len(records) != 1 {
		t.Fatalf("expected 1 record, got %d", len(records))
	}

	got := records[0]
	if got.OrgID != record.OrgID {
		t.Fatalf("expected OrgID=%d, got %d", record.OrgID, got.OrgID)
	}
	if got.ModelID != record.ModelID {
		t.Fatalf("expected ModelID=%d, got %d", record.ModelID, got.ModelID)
	}
	if got.Provider != record.Provider {
		t.Fatalf("expected Provider=%q, got %q", record.Provider, got.Provider)
	}
	if got.ModelName != record.ModelName {
		t.Fatalf("expected ModelName=%q, got %q", record.ModelName, got.ModelName)
	}
	if got.EntryProtocol != record.EntryProtocol {
		t.Fatalf("expected EntryProtocol=%q, got %q", record.EntryProtocol, got.EntryProtocol)
	}
	if got.IsStream != record.IsStream {
		t.Fatalf("expected IsStream=%v, got %v", record.IsStream, got.IsStream)
	}
	if got.InputTokens != record.InputTokens {
		t.Fatalf("expected InputTokens=%d, got %d", record.InputTokens, got.InputTokens)
	}
	if got.OutputTokens != record.OutputTokens {
		t.Fatalf("expected OutputTokens=%d, got %d", record.OutputTokens, got.OutputTokens)
	}
	if got.TotalTokens != record.TotalTokens {
		t.Fatalf("expected TotalTokens=%d, got %d", record.TotalTokens, got.TotalTokens)
	}
	if got.LatencyMS != record.LatencyMS {
		t.Fatalf("expected LatencyMS=%d, got %d", record.LatencyMS, got.LatencyMS)
	}
	if got.StatusCode != record.StatusCode {
		t.Fatalf("expected StatusCode=%d, got %d", record.StatusCode, got.StatusCode)
	}
	if got.Success != record.Success {
		t.Fatalf("expected Success=%v, got %v", record.Success, got.Success)
	}
	if got.Message != record.Message {
		t.Fatalf("expected Message=%q, got %q", record.Message, got.Message)
	}
	if got.CallerType != record.CallerType {
		t.Fatalf("expected CallerType=%q, got %q", record.CallerType, got.CallerType)
	}
	if got.ReqID != record.ReqID {
		t.Fatalf("expected ReqID=%q, got %q", record.ReqID, got.ReqID)
	}
	if got.ProjectID != record.ProjectID {
		t.Fatalf("expected ProjectID=%d, got %d", record.ProjectID, got.ProjectID)
	}
	if got.SessionID != record.SessionID {
		t.Fatalf("expected SessionID=%d, got %d", record.SessionID, got.SessionID)
	}
	if got.MessageID != record.MessageID {
		t.Fatalf("expected MessageID=%d, got %d", record.MessageID, got.MessageID)
	}
	if got.AssistantID != record.AssistantID {
		t.Fatalf("expected AssistantID=%d, got %d", record.AssistantID, got.AssistantID)
	}
	if got.Uin != record.Uin {
		t.Fatalf("expected Uin=%d, got %d", record.Uin, got.Uin)
	}
}

func TestRecorderListCallsWithFilters(t *testing.T) {
	recorder := setupRecorderDB(t)
	ctx := context.Background()
	now := time.Now()

	records := []*CallRecord{
		{OrgID: testOrgID, Provider: "openai", CallerType: "worker", Success: true, StartedAt: now, FinishedAt: now},
		{OrgID: testOrgID, Provider: "openai", CallerType: "api", Success: false, Message: "timeout", StartedAt: now, FinishedAt: now},
		{OrgID: testOrgID, Provider: "deepseek", CallerType: "worker", Success: true, StartedAt: now, FinishedAt: now},
	}
	for i, r := range records {
		if err := recorder.RecordCall(ctx, r); err != nil {
			t.Fatalf("RecordCall[%d] failed: %v", i, err)
		}
	}

	time.Sleep(50 * time.Millisecond)

	provider := "openai"
	records, total, err := recorder.ListCalls(ctx, testOrgID, 0, 50, nil, &provider, nil, nil)
	if err != nil {
		t.Fatalf("ListCalls by provider failed: %v", err)
	}
	if total != 2 {
		t.Fatalf("expected 2 openai records, got %d", total)
	}

	callerType := "worker"
	_, total, err = recorder.ListCalls(ctx, testOrgID, 0, 50, nil, nil, &callerType, nil)
	if err != nil {
		t.Fatalf("ListCalls by callerType failed: %v", err)
	}
	if total != 2 {
		t.Fatalf("expected 2 worker records, got %d", total)
	}

	failed := false
	_, total, err = recorder.ListCalls(ctx, testOrgID, 0, 50, nil, nil, nil, &failed)
	if err != nil {
		t.Fatalf("ListCalls by success=false failed: %v", err)
	}
	if total != 1 {
		t.Fatalf("expected 1 failed record, got %d", total)
	}
}

func TestRecorderRecordCallNilRecord(t *testing.T) {
	recorder := setupRecorderDB(t)
	if err := recorder.RecordCall(context.Background(), nil); err != nil {
		t.Fatalf("RecordCall(nil) should not error, got: %v", err)
	}
}

func TestCallRecordToEntityNil(t *testing.T) {
	if e := callRecordToEntity(nil); e != nil {
		t.Fatal("expected nil for nil input")
	}
}

func TestCallRecordFromEntityNil(t *testing.T) {
	if r := callRecordFromEntity(nil); r != nil {
		t.Fatal("expected nil for nil input")
	}
}

func TestCallRecordToEntityPreservesIDWhenSet(t *testing.T) {
	r := &CallRecord{ID: 42, OrgID: 1}
	e := callRecordToEntity(r)
	if e.ID != 42 {
		t.Fatalf("expected ID=42, got %d", e.ID)
	}
}
