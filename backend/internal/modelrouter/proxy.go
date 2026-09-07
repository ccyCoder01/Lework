package modelrouter

import "strings"

// ProxyBaseURL returns the built-in worker model proxy BaseURL.
// workerAddr is the worker's listen address (e.g., ":8081" or "127.0.0.1:8081").
// Requests sent to this address are transparently routed to the upstream provider
// according to the config registered in the worker-scoped ModelStore.
//
// Returns empty string when workerAddr is empty.
func ProxyBaseURL(workerAddr string) string {
	addr := strings.TrimSpace(workerAddr)
	if addr == "" {
		return ""
	}
	addr = strings.TrimRight(addr, "/")
	if strings.HasPrefix(addr, "http://") || strings.HasPrefix(addr, "https://") {
		return ensureV1Suffix(addr)
	}
	if strings.HasPrefix(addr, ":") {
		return ensureV1Suffix("http://127.0.0.1" + addr)
	}
	return ensureV1Suffix("http://" + addr)
}

// ensureV1Suffix ensures the BaseURL ends with /v1 if needed.
func ensureV1Suffix(baseURL string) string {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" || strings.HasSuffix(baseURL, "/v1") {
		return baseURL
	}
	return baseURL + "/v1"
}
