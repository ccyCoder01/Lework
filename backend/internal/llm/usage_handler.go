package llm

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

// RegisterUsageRoute registers the internal usage report endpoint on the given router.
// This route should be mounted on a group that does not require RequireCallerOrg
// (it uses worker token auth).
func RegisterUsageRoute(r gin.IRouter, recorder Recorder) {
	r.POST("/llm/usage", handleUsageReport(recorder))
}

func handleUsageReport(recorder Recorder) gin.HandlerFunc {
	return func(c *gin.Context) {
		var payload usageReportPayload
		if err := c.ShouldBindJSON(&payload); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}

		now := time.Now()
		record := &CallRecord{
			OrgID:           payload.OrgID,
			ModelID:         payload.ModelID,
			Provider:        payload.Provider,
			ModelName:       payload.ModelName,
			ModelProvider:   payload.ModelProvider,
			EntryProtocol:   payload.EntryProtocol,
			IsStream:        payload.IsStream,
			InputTokens:     payload.InputTokens,
			OutputTokens:    payload.OutputTokens,
			TotalTokens:     payload.TotalTokens,
			LatencyMS:       payload.LatencyMS,
			PromptTokens:    payload.PromptTokens,
			CacheHitTokens:  payload.CacheHitTokens,
			CacheMissTokens: payload.CacheMissTokens,
			StatusCode:      payload.StatusCode,
			Success:         payload.Success,
			Status:          payload.Status,
			Message:         payload.Message,
			CallerType:      payload.CallerType,
			ReqID:           payload.ReqID,
			TraceID:         payload.TraceID,
			RetryTimes:      payload.RetryTimes,
			InputLen:        payload.InputLen,
			OutputLen:       payload.OutputLen,
			InputTruncated:  payload.InputTruncated,
			OutputTruncated: payload.OutputTruncated,
			ClientIP:        payload.ClientIP,
			ProjectID:       payload.ProjectID,
			SessionID:       payload.SessionID,
			MessageID:       payload.MessageID,
			AssistantID:     payload.AssistantID,
			Uin:             payload.Uin,
			Input:           payload.Input,
			Output:          payload.Output,
			StartedAt:       payload.StartedAt,
			FinishedAt:      payload.FinishedAt,
		}
		if record.StartedAt.IsZero() {
			record.StartedAt = now
		}
		if record.FinishedAt.IsZero() {
			record.FinishedAt = now
		}

		if err := recorder.RecordCall(c.Request.Context(), record); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"ok": true})
	}
}
