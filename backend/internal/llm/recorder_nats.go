package llm

import (
	"context"
	"encoding/json"

	"github.com/insmtx/Leros/backend/pkg/messaging"
	"github.com/ygpkg/yg-go/logs"
)

// RecordPublisher 是对外发布 CallRecord 的最小抽象。
type RecordPublisher interface {
	PublishUsage(ctx context.Context, record *CallRecord) error
}

// UsageSubscriber 是订阅 usage 事件的抽象，server 端用 eventbus.Subscriber 实现。
type UsageSubscriber interface {
	Subscribe(ctx context.Context, topic string, consumer string, handler func(data []byte)) error
}

// RecorderNATS 通过 NATS JetStream 将 LLM 调用记录发布到 server 端。
type RecorderNATS struct {
	pub   RecordPublisher
	orgID uint
}

var _ Recorder = (*RecorderNATS)(nil)

// NewRecorderNATS 创建一个基于 NATS 的 Recorder 实现。
func NewRecorderNATS(pub RecordPublisher, orgID uint) *RecorderNATS {
	return &RecorderNATS{pub: pub, orgID: orgID}
}

// RecordCall 将调用记录发布到 LLM_USAGE_STREAM。
func (r *RecorderNATS) RecordCall(ctx context.Context, record *CallRecord) error {
	if r.pub == nil {
		return nil
	}
	return r.pub.PublishUsage(ctx, record)
}

// ListCalls 不支持，NATS 端不负责查询。
func (r *RecorderNATS) ListCalls(ctx context.Context, orgID uint, offset, limit int,
	modelID *uint, provider, callerType *string, success *bool) ([]*CallRecord, int64, error) {
	return nil, 0, nil
}

// Shutdown 空实现，NATS recorder 不管理本地 goroutine。
func (r *RecorderNATS) Shutdown(ctx context.Context) error {
	return nil
}

// LLMUsagePublisher 将 eventbus.Publisher 适配为 RecordPublisher。
type LLMUsagePublisher struct {
	publishFn func(ctx context.Context, subject string, event any) error
}

// NewLLMUsagePublisher 创建适配器。
func NewLLMUsagePublisher(publishFn func(ctx context.Context, subject string, event any) error) *LLMUsagePublisher {
	return &LLMUsagePublisher{publishFn: publishFn}
}

// PublishUsage 将 CallRecord 发布到 org.<org_id>.usage.llm。
func (p *LLMUsagePublisher) PublishUsage(ctx context.Context, record *CallRecord) error {
	subject, err := messaging.LLMUsageSubject(record.OrgID)
	if err != nil {
		return err
	}
	return p.publishFn(ctx, subject, record)
}

// StartUsageConsumer 在 server 端订阅 LLM usage 事件并写入数据库。
func StartUsageConsumer(ctx context.Context, recorder Recorder, sub UsageSubscriber) {
	const consumer = "llm-usage-consumer"

	for {
		select {
		case <-ctx.Done():
			logs.InfoContextf(ctx, "llm usage consumer stopped")
			return
		default:
		}

		finished := make(chan struct{}, 1)
		go func() {
			defer func() {
				if r := recover(); r != nil {
					logs.ErrorContextf(ctx, "llm usage consumer panicked: %v", r)
				}
				finished <- struct{}{}
			}()
			topic := messaging.LLMUsageWildcard()
			err := sub.Subscribe(ctx, topic, consumer, func(data []byte) {
				var record CallRecord
				if err := json.Unmarshal(data, &record); err != nil {
					logs.ErrorContextf(ctx, "llm usage consumer: unmarshal failed: %v", err)
					return
				}
				if err := recorder.RecordCall(ctx, &record); err != nil {
					logs.ErrorContextf(ctx, "llm usage consumer: RecordCall failed: %v", err)
				}
			})
			if err != nil {
				logs.ErrorContextf(ctx, "llm usage consumer: subscribe failed: %v", err)
			}
		}()

		<-finished

		if ctx.Err() != nil {
			return
		}
		logs.WarnContextf(ctx, "llm usage consumer exited, restarting...")
	}
}
