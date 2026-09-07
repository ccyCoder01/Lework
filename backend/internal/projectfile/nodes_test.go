package projectfile_test

import (
	"testing"

	"github.com/insmtx/Leros/backend/internal/consts"
	"github.com/insmtx/Leros/backend/internal/projectfile"
)

func TestNormalizeFolderRelativePath(t *testing.T) {
	path, err := projectfile.NormalizeFolderRelativePath(consts.RepoDirUploads + "/demo")
	if err != nil {
		t.Fatalf("NormalizeFolderRelativePath() error = %v", err)
	}
	if path != consts.RepoDirUploads+"/demo/" {
		t.Fatalf("path = %q, want uploads/demo/", path)
	}
}
