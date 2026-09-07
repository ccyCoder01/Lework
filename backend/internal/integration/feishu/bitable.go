package feishu

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"strings"
	"sync"
	"time"
)

const (
	defaultBaseURL     = "https://open.feishu.cn"
	tokenRefreshBuffer = 5 * time.Minute
)

// Client talks to Feishu Open Platform for Bitable record creation.
type Client struct {
	baseURL   string
	appID     string
	appSecret string
	appToken  string
	tableID   string
	http      *http.Client

	mu          sync.Mutex
	accessToken string
	tokenExpiry time.Time
}

// NewClient creates a Feishu Bitable client.
func NewClient(appID, appSecret, appToken, tableID string) *Client {
	return &Client{
		baseURL:   defaultBaseURL,
		appID:     strings.TrimSpace(appID),
		appSecret: strings.TrimSpace(appSecret),
		appToken:  strings.TrimSpace(appToken),
		tableID:   strings.TrimSpace(tableID),
		http:      &http.Client{Timeout: 30 * time.Second},
	}
}

type apiResponse struct {
	Code int             `json:"code"`
	Msg  string          `json:"msg"`
	Data json.RawMessage `json:"data"`
}

type tokenResponse struct {
	Code              int    `json:"code"`
	Msg               string `json:"msg"`
	TenantAccessToken string `json:"tenant_access_token"`
	Expire            int    `json:"expire"`
}

type createRecordResponse struct {
	Record struct {
		RecordID string `json:"record_id"`
	} `json:"record"`
}

// CreateFeedbackRecord writes one row into the configured feedback Bitable table.
func (c *Client) CreateFeedbackRecord(ctx context.Context, fields map[string]any) (string, error) {
	if c == nil {
		return "", fmt.Errorf("feishu client is nil")
	}
	if c.appToken == "" || c.tableID == "" {
		return "", fmt.Errorf("feishu bitable app_token or table_id is not configured")
	}

	token, err := c.tenantAccessToken(ctx)
	if err != nil {
		return "", err
	}

	body, err := json.Marshal(map[string]any{"fields": fields})
	if err != nil {
		return "", fmt.Errorf("marshal create record body: %w", err)
	}

	url := fmt.Sprintf("%s/open-apis/bitable/v1/apps/%s/tables/%s/records", c.baseURL, c.appToken, c.tableID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("create record request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json; charset=utf-8")

	resp, err := c.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("create record request failed: %w", err)
	}
	defer resp.Body.Close()

	var parsed apiResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return "", fmt.Errorf("decode create record response: %w", err)
	}
	if parsed.Code != 0 {
		return "", fmt.Errorf("feishu create record failed: code=%d msg=%s", parsed.Code, parsed.Msg)
	}

	var data createRecordResponse
	if err := json.Unmarshal(parsed.Data, &data); err != nil {
		return "", fmt.Errorf("decode create record data: %w", err)
	}
	if data.Record.RecordID == "" {
		return "", fmt.Errorf("feishu create record returned empty record_id")
	}
	return data.Record.RecordID, nil
}

// UploadAttachment uploads one file into the Bitable and returns file_token.
func (c *Client) UploadAttachment(ctx context.Context, filename string, content []byte, isImage bool) (string, error) {
	if c == nil {
		return "", fmt.Errorf("feishu client is nil")
	}
	if c.appToken == "" {
		return "", fmt.Errorf("feishu bitable app_token is not configured")
	}

	token, err := c.tenantAccessToken(ctx)
	if err != nil {
		return "", err
	}

	parentType := "bitable_file"
	if isImage {
		parentType = "bitable_image"
	}

	var body bytes.Buffer
	writer := multipart.NewWriter(&body)
	_ = writer.WriteField("file_name", filename)
	_ = writer.WriteField("parent_type", parentType)
	_ = writer.WriteField("parent_node", c.appToken)
	_ = writer.WriteField("size", fmt.Sprintf("%d", len(content)))

	part, err := writer.CreateFormFile("file", filename)
	if err != nil {
		return "", fmt.Errorf("create multipart file field: %w", err)
	}
	if _, err := part.Write(content); err != nil {
		return "", fmt.Errorf("write multipart file content: %w", err)
	}
	if err := writer.Close(); err != nil {
		return "", fmt.Errorf("close multipart writer: %w", err)
	}

	url := c.baseURL + "/open-apis/drive/v1/medias/upload_all"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, &body)
	if err != nil {
		return "", fmt.Errorf("create upload request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", writer.FormDataContentType())

	resp, err := c.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("upload attachment request failed: %w", err)
	}
	defer resp.Body.Close()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read upload response: %w", err)
	}

	var parsed apiResponse
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return "", fmt.Errorf("decode upload response: %w", err)
	}
	if parsed.Code != 0 {
		return "", fmt.Errorf("feishu upload attachment failed: code=%d msg=%s", parsed.Code, parsed.Msg)
	}

	var data struct {
		FileToken string `json:"file_token"`
	}
	if err := json.Unmarshal(parsed.Data, &data); err != nil {
		return "", fmt.Errorf("decode upload data: %w", err)
	}
	if data.FileToken == "" {
		return "", fmt.Errorf("feishu upload attachment returned empty file_token")
	}
	return data.FileToken, nil
}

func (c *Client) tenantAccessToken(ctx context.Context) (string, error) {
	c.mu.Lock()
	if c.accessToken != "" && time.Now().Before(c.tokenExpiry) {
		token := c.accessToken
		c.mu.Unlock()
		return token, nil
	}
	c.mu.Unlock()

	if c.appID == "" || c.appSecret == "" {
		return "", fmt.Errorf("feishu app_id or app_secret is not configured")
	}

	body, err := json.Marshal(map[string]string{
		"app_id":     c.appID,
		"app_secret": c.appSecret,
	})
	if err != nil {
		return "", fmt.Errorf("marshal token request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/open-apis/auth/v3/tenant_access_token/internal", bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("create token request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("token request failed: %w", err)
	}
	defer resp.Body.Close()

	var parsed tokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&parsed); err != nil {
		return "", fmt.Errorf("decode token response: %w", err)
	}
	if parsed.Code != 0 || parsed.TenantAccessToken == "" {
		return "", fmt.Errorf("feishu token failed: code=%d msg=%s", parsed.Code, parsed.Msg)
	}

	expire := time.Duration(parsed.Expire) * time.Second
	if expire <= 0 {
		expire = 2 * time.Hour
	}

	c.mu.Lock()
	c.accessToken = parsed.TenantAccessToken
	c.tokenExpiry = time.Now().Add(expire - tokenRefreshBuffer)
	c.mu.Unlock()

	return parsed.TenantAccessToken, nil
}
