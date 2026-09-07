package sms

import (
	"crypto/hmac"
	"crypto/sha1"
	"encoding/base64"
	"errors"
	"net/url"
	"sort"
	"strings"
)

// ErrRateLimited signals that the SMS provider rejected the request because of
// rate limiting (flow control). Callers may translate it to a domain-specific
// "send too often" error.
var ErrRateLimited = errors.New("aliyun sms rate limited")

func aliyunSignature(values url.Values, accessKeySecret string) string {
	keys := make([]string, 0, len(values))
	for key := range values {
		if key == "Signature" {
			continue
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)

	encoded := make([]string, 0, len(keys))
	for _, key := range keys {
		encoded = append(encoded, aliyunPercentEncode(key)+"="+aliyunPercentEncode(values.Get(key)))
	}
	stringToSign := "GET&%2F&" + aliyunPercentEncode(strings.Join(encoded, "&"))
	mac := hmac.New(sha1.New, []byte(accessKeySecret+"&"))
	mac.Write([]byte(stringToSign))
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

func aliyunPercentEncode(value string) string {
	encoded := url.QueryEscape(value)
	encoded = strings.ReplaceAll(encoded, "+", "%20")
	encoded = strings.ReplaceAll(encoded, "*", "%2A")
	encoded = strings.ReplaceAll(encoded, "%7E", "~")
	return encoded
}

func isAliyunSMSRateLimited(code string, message string) bool {
	switch strings.TrimSpace(code) {
	case "isv.BUSINESS_LIMIT_CONTROL", "isv.DAY_LIMIT_CONTROL", "isv.MONTH_LIMIT_CONTROL":
		return true
	}

	trimmedMessage := strings.TrimSpace(message)
	if trimmedMessage == "" {
		return false
	}

	return strings.Contains(trimmedMessage, "流控") ||
		strings.Contains(trimmedMessage, "Permits") ||
		strings.Contains(trimmedMessage, "频率") ||
		strings.Contains(trimmedMessage, "过于频繁")
}
