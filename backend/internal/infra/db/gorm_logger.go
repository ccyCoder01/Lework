package db

import (
	"context"
	"fmt"
	"time"

	"github.com/ygpkg/yg-go/apis/constants"
	"go.uber.org/zap"
	gormlogger "gorm.io/gorm/logger"
)

type contextGormLogger struct {
	logger *zap.SugaredLogger
}

func newContextGormLogger(logger *zap.SugaredLogger) gormlogger.Interface {
	return &contextGormLogger{
		logger: logger.Desugar().WithOptions(zap.AddCallerSkip(2)).Sugar(),
	}
}

func (l *contextGormLogger) LogMode(gormlogger.LogLevel) gormlogger.Interface {
	return l
}

func (l *contextGormLogger) Info(_ context.Context, message string, data ...interface{}) {
	l.logger.Infof(message, data...)
}

func (l *contextGormLogger) Warn(_ context.Context, message string, data ...interface{}) {
	l.logger.Warnf(message, data...)
}

func (l *contextGormLogger) Error(_ context.Context, message string, data ...interface{}) {
	l.logger.Errorf(message, data...)
}

func (l *contextGormLogger) Trace(
	ctx context.Context,
	begin time.Time,
	query func() (sql string, rowsAffected int64),
	err error,
) {
	requestID, _ := ctx.Value(constants.CtxKeyRequestID).(string)
	elapsed := time.Since(begin)
	sql, rows := query()
	fields := []interface{}{
		"req_id", requestID,
		"elapsed", fmt.Sprintf("%vms", elapsed.Nanoseconds()/1e6),
		"rows", rows,
	}
	if err != nil {
		l.logger.With(append(fields, "error", err)...).Warn(sql)
		return
	}
	l.logger.With(fields...).Debug(sql)
}
