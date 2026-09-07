package skillstate

import (
	"os"
	"path/filepath"
	"testing"
)

func TestManifestParsesLegacyAndCurrentPolicies(t *testing.T) {
	hashA := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	hashB := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	manifest := Parse([]byte(
		"legacy:" + hashA + ":1\n" +
			"connector:" + hashB + ":2:local_only\n",
	))
	if len(manifest.Warnings) != 0 || len(manifest.Records) != 2 {
		t.Fatalf("manifest = %#v", manifest)
	}
	if manifest.Records["legacy"].SyncPolicy != SyncPolicyPublish {
		t.Fatalf("legacy policy = %q", manifest.Records["legacy"].SyncPolicy)
	}
	if manifest.Records["connector"].SyncPolicy != SyncPolicyLocalOnly {
		t.Fatalf("connector policy = %q", manifest.Records["connector"].SyncPolicy)
	}
}

func TestManifestWriteUsesCurrentFormat(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".seed-manifest")
	hash := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	if err := Write(path, map[string]InstallRecord{
		"connector": {SHA256: hash, Revision: 3, SyncPolicy: SyncPolicyLocalOnly},
	}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := string(raw), "connector:"+hash+":3:local_only\n"; got != want {
		t.Fatalf("manifest = %q, want %q", got, want)
	}
}
