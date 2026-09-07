package db

import (
	"strings"
)

// IsUniqueConstraintError reports whether err indicates a unique/duplicate
// constraint violation from the underlying database driver. It inspects the
// error message because GORM does not expose a typed sentinel across all
// supported drivers (SQLite, Postgres, MySQL).
func IsUniqueConstraintError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "unique") || strings.Contains(msg, "duplicate")
}
