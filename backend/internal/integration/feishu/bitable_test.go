package feishu

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestCreateFeedbackRecord(t *testing.T) {
	t.Parallel()

	var gotAuth string
	var gotBody map[string]any

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/open-apis/auth/v3/tenant_access_token/internal":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"code":                0,
				"tenant_access_token": "tenant-token",
				"expire":              7200,
			})
		case strings.Contains(r.URL.Path, "/open-apis/bitable/v1/apps/"):
			gotAuth = r.Header.Get("Authorization")
			_ = json.NewDecoder(r.Body).Decode(&gotBody)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"code": 0,
				"data": map[string]any{
					"record": map[string]any{"record_id": "recTEST"},
				},
			})
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewClient("app-id", "app-secret", "app-token", "table-id")
	client.baseURL = server.URL

	recordID, err := client.CreateFeedbackRecord(context.Background(), map[string]any{
		"问题名称": "测试",
		"问题描述": "内容",
		"问题类型": "BUG",
	})
	if err != nil {
		t.Fatalf("CreateFeedbackRecord() error = %v", err)
	}
	if recordID != "recTEST" {
		t.Fatalf("recordID = %q, want recTEST", recordID)
	}
	if gotAuth != "Bearer tenant-token" {
		t.Fatalf("auth header = %q", gotAuth)
	}
	fields, ok := gotBody["fields"].(map[string]any)
	if !ok {
		t.Fatalf("fields payload missing: %#v", gotBody)
	}
	if fields["问题类型"] != "BUG" {
		t.Fatalf("fields = %#v", fields)
	}
}

func TestUploadAttachment(t *testing.T) {
	t.Parallel()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/open-apis/auth/v3/tenant_access_token/internal":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"code":                0,
				"tenant_access_token": "tenant-token",
				"expire":              7200,
			})
		case r.URL.Path == "/open-apis/drive/v1/medias/upload_all":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"code": 0,
				"data": map[string]any{"file_token": "boxTEST"},
			})
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewClient("app-id", "app-secret", "app-token", "table-id")
	client.baseURL = server.URL

	token, err := client.UploadAttachment(context.Background(), "demo.png", []byte("png"), true)
	if err != nil {
		t.Fatalf("UploadAttachment() error = %v", err)
	}
	if token != "boxTEST" {
		t.Fatalf("token = %q, want boxTEST", token)
	}
}
