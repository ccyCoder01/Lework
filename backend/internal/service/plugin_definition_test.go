package service

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/url"
	"strings"
	"testing"
)

func TestPluginIdentityFromSkillArchiveUsesManifestName(t *testing.T) {
	var buf bytes.Buffer
	writer := zip.NewWriter(&buf)
	entry, err := writer.Create("demo/SKILL.md")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := entry.Write([]byte("---\nname: release-notes\ndescription: Release notes helper\n---\n\nWrite release notes.")); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	code, name, description, err := pluginIdentityFromSkillArchive(buf.Bytes())
	if err != nil || code != "release-notes" || name != "release-notes" || description != "Release notes helper" {
		t.Fatalf("identity=%q,%q,%q err=%v", code, name, description, err)
	}
}

func TestNormalizeSkillArchiveStripsSkillParentDirectory(t *testing.T) {
	archive := testSkillArchive(t, map[string]string{
		"bundle/SKILL.md":          "---\nname: release-notes\ndescription: Release notes helper\n---\n\nWrite release notes.",
		"bundle/references/api.md": "API reference",
		"outside/ignored.md":       "must not be packaged",
	})
	normalized, changed, err := normalizeSkillArchive(archive)
	if err != nil {
		t.Fatalf("normalize skill archive: %v", err)
	}
	if !changed {
		t.Fatal("nested skill archive must be normalized")
	}
	reader, err := zip.NewReader(bytes.NewReader(normalized), int64(len(normalized)))
	if err != nil {
		t.Fatal(err)
	}
	entries := make(map[string]bool)
	for _, file := range reader.File {
		entries[file.Name] = true
	}
	if !entries["SKILL.md"] || !entries["references/api.md"] || entries["bundle/SKILL.md"] || entries["outside/ignored.md"] {
		t.Fatalf("normalized archive entries = %#v", entries)
	}
}

func TestNormalizeSkillArchiveRetainsRootDirectoryPackage(t *testing.T) {
	archive := testSkillArchive(t, map[string]string{
		"SKILL.md":          "---\nname: release-notes\ndescription: Release notes helper\n---\n\nWrite release notes.",
		"references/api.md": "API reference",
	})
	normalized, changed, err := normalizeSkillArchive(archive)
	if err != nil {
		t.Fatalf("normalize root skill archive: %v", err)
	}
	if changed || !bytes.Equal(normalized, archive) {
		t.Fatal("root skill archive must be retained without repackaging")
	}
}

func TestBuildSkillRevisionContentStoresRawEntrypointAndSortedFiles(t *testing.T) {
	rawSkillMD := "---\nname: release-notes\ndescription: Release notes helper\n---\n\n# Release notes"
	archive := testSkillArchive(t, map[string]string{
		"scripts/z.sh":    "z",
		"SKILL.md":        rawSkillMD,
		"references/a.md": "a",
		"scripts/a.sh":    "a",
	})
	hash := sha256.Sum256(archive)
	draft, err := buildSkillRevisionContent(archive, hex.EncodeToString(hash[:]))
	if err != nil {
		t.Fatalf("build Skill revision content: %v", err)
	}
	if draft.EntrypointContent != rawSkillMD {
		t.Fatalf("entrypoint content = %q", draft.EntrypointContent)
	}
	gotPaths := make([]string, 0, len(draft.FileIndex))
	for _, file := range draft.FileIndex {
		gotPaths = append(gotPaths, file.Path)
		if len(file.SHA256) != 64 {
			t.Fatalf("file %s SHA-256 = %q", file.Path, file.SHA256)
		}
	}
	wantPaths := []string{"SKILL.md", "references/a.md", "scripts/a.sh", "scripts/z.sh"}
	if len(gotPaths) != len(wantPaths) {
		t.Fatalf("file paths = %#v", gotPaths)
	}
	for index := range wantPaths {
		if gotPaths[index] != wantPaths[index] {
			t.Fatalf("file paths = %#v, want %#v", gotPaths, wantPaths)
		}
	}
}

func TestValidatePluginDefinition(t *testing.T) {
	cases := []struct {
		kind       string
		definition string
		ok         bool
	}{
		{"skill", `{"schema":"skill/v1","artifact":{"file_upload_id":"file_demo","sha256":"abc","size_bytes":1,"content_type":"application/zip"}}`, true},
		{"mcp", `{"schema":"mcp/v1","transport":"http","url":"https://mcp.example.com","secret_refs":{"authorization":"sec_1"}}`, true},
		{"mcp", `{"schema":"mcp/v1","transport":"stdio","command":"mcp-server","args":[],"env_secret_refs":{"TOKEN":"sec_1"}}`, true},
		{"workflow", `{"schema":"workflow/v1","definition":{"steps":[]}}`, true},
		{"mcp", `{"schema":"mcp/v1","transport":"http","url":"https://mcp.example.com","token":"plaintext"}`, true},
		{"unknown", `{"schema":"unknown/v1"}`, false},
	}
	for _, tc := range cases {
		err := ValidatePluginDefinition(tc.kind, json.RawMessage(tc.definition))
		if (err == nil) != tc.ok {
			t.Errorf("ValidatePluginDefinition(%s) error=%v, want ok=%v", tc.kind, err, tc.ok)
		}
	}
}

func TestArtifactFromDefinition(t *testing.T) {
	artifact, err := ArtifactFromDefinition("skill", json.RawMessage(`{"schema":"skill/v1","artifact":{"file_upload_id":"file_demo","sha256":"abc"}}`))
	if err != nil || artifact == nil || artifact.FileUploadID != "file_demo" || artifact.SHA256 != "abc" {
		t.Fatalf("artifact = %#v, %v", artifact, err)
	}
}

func TestRenderConnectorBindingSupportsDirectAndTemplateValues(t *testing.T) {
	values := map[string]string{"api_key": "secret", "tenant": "acme"}
	cases := []struct {
		name       string
		expression string
		want       string
		wantOK     bool
		wantError  bool
	}{
		{name: "direct", expression: "api_key", want: "secret", wantOK: true},
		{name: "bearer", expression: "Bearer {{api_key}}", want: "Bearer secret", wantOK: true},
		{name: "multiple", expression: "{{tenant}}:{{api_key}}", want: "acme:secret", wantOK: true},
		{name: "missing", expression: "Bearer {{missing}}", wantOK: false},
		{name: "malformed", expression: "Bearer {{api_key}", wantError: true},
		{name: "static", expression: "Bearer static-secret", wantError: true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok, err := RenderConnectorBinding(tc.expression, values)
			if (err != nil) != tc.wantError || ok != tc.wantOK || got != tc.want {
				t.Fatalf("RenderConnectorBinding() = %q, %t, %v", got, ok, err)
			}
		})
	}
}

func TestMCPFromDefinitionRendersGenericBindings(t *testing.T) {
	raw := json.RawMessage(`{"schema":"connector/v1","channel":"catapi","mode":"mcp_only",` +
		`"auth":{"type":"form","values":{"api_key":"secret","tenant":"acme"},"bindings":{` +
		`"mcp_headers":{"Authorization":"Bearer {{api_key}}","X-Tenant":"tenant"},` +
		`"mcp_env":{"CATAPI_KEY":"{{api_key}}"},"mcp_query":{"tenant":"{{tenant}}"}}},` +
		`"mcp":{"schema":"mcp/v1","transport":"http","name":"catapi",` +
		`"url":"https://api.example.com/mcp?fixed=one"}}`)
	mcp, err := MCPFromDefinition(raw)
	if err != nil {
		t.Fatalf("MCPFromDefinition() error = %v", err)
	}
	parsed, err := url.Parse(mcp.URL)
	if err != nil {
		t.Fatalf("parse rendered URL: %v", err)
	}
	if mcp.Headers["Authorization"] != "Bearer secret" || mcp.Headers["X-Tenant"] != "acme" ||
		mcp.Env["CATAPI_KEY"] != "secret" || parsed.Query().Get("tenant") != "acme" ||
		parsed.Query().Get("fixed") != "one" {
		t.Fatalf("rendered MCP definition = %#v", mcp)
	}
}

func TestMCPFromDefinitionSkipsBindingsWithEmptyCredentials(t *testing.T) {
	raw := json.RawMessage(`{"schema":"connector/v1","channel":"catapi","mode":"mcp_only",` +
		`"auth":{"type":"form","values":{},"bindings":{` +
		`"mcp_headers":{"Authorization":"Bearer {{api_key}}"},"mcp_query":{"key":"api_key"}}},` +
		`"mcp":{"schema":"mcp/v1","transport":"http","name":"catapi","url":"https://api.example.com/mcp"}}`)
	mcp, err := MCPFromDefinition(raw)
	if err != nil || mcp == nil {
		t.Fatalf("MCPFromDefinition() = %#v, %v", mcp, err)
	}
	if mcp.Headers["Authorization"] != "" || strings.Contains(mcp.URL, "key=") {
		t.Fatalf("empty credentials produced runtime bindings: %#v", mcp)
	}
}

func TestMCPFromDefinitionReadsLegacyBearerBinding(t *testing.T) {
	raw := json.RawMessage(`{"schema":"connector/v1","channel":"corekg","mode":"mcp_only",` +
		`"auth":{"type":"managed","values":{"api_key":"legacy-secret"},` +
		`"bindings":{"mcp_bearer_token":"api_key"}},` +
		`"mcp":{"schema":"mcp/v1","transport":"http","name":"corekg","url":"https://api.example.com/mcp"}}`)
	mcp, err := MCPFromDefinition(raw)
	if err != nil || mcp == nil || mcp.BearerToken != "legacy-secret" {
		t.Fatalf("legacy MCP definition = %#v, %v", mcp, err)
	}
}

func testSkillArchive(t *testing.T, entries map[string]string) []byte {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, content := range entries {
		entry, err := writer.Create(name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write([]byte(content)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}
