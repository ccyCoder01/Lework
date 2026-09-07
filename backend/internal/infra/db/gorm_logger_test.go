package db

import (
	"context"
	"testing"
	"time"

	"github.com/ygpkg/yg-go/apis/constants"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"go.uber.org/zap/zaptest/observer"
)

func TestContextGormLoggerUsesUnifiedRequestIDField(t *testing.T) {
	core, observed := observer.New(zapcore.DebugLevel)
	logger := newContextGormLogger(zap.New(core).Sugar())
	ctx := context.WithValue(context.Background(), constants.CtxKeyRequestID, "request-1")

	logger.Trace(ctx, time.Now(), func() (string, int64) {
		return "SELECT 1", 1
	}, nil)

	entries := observed.All()
	if len(entries) != 1 {
		t.Fatalf("log entries = %d, want 1", len(entries))
	}
	fields := entries[0].ContextMap()
	if fields["req_id"] != "request-1" {
		t.Fatalf("req_id = %#v, want request-1", fields["req_id"])
	}
	if _, exists := fields["reqid"]; exists {
		t.Fatalf("legacy reqid field should not exist: %#v", fields["reqid"])
	}
}
