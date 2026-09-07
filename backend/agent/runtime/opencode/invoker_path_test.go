package opencode

import (
	"strings"
	"testing"
)

func TestOpenCodeUsesConfiguredDataDirForConfig(t *testing.T) {
	dataDir := t.TempDir()
	env := buildOpenCodeInvocationEnv(
		[]string{"OPENCODE_CONFIG_DIR=/inherited/config"},
		[]string{"OPENCODE_CONFIG_DIR=/task/config"},
		dataDir,
	)

	assertEnvContains(t, env, "OPENCODE_CONFIG_DIR="+dataDir)
	for _, item := range env {
		if item == "OPENCODE_CONFIG_DIR=/inherited/config" || item == "OPENCODE_CONFIG_DIR=/task/config" {
			t.Fatalf("non-fixed OpenCode config dir remained: %q", item)
		}
	}
}

func TestOpenCodeOmitsConfigDirWhenDataDirIsEmpty(t *testing.T) {
	env := buildOpenCodeInvocationEnv(nil, nil, " ")
	for _, item := range env {
		if strings.HasPrefix(item, "OPENCODE_CONFIG_DIR=") {
			t.Fatalf("unexpected empty OpenCode config dir: %q", item)
		}
	}
}
