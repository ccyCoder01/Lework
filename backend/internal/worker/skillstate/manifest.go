// Package skillstate owns the Worker-local installed Skill manifest contract.
package skillstate

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

// SyncPolicy controls whether a changed installed Skill may be published.
type SyncPolicy string

const (
	SyncPolicyPublish   SyncPolicy = "publish"
	SyncPolicyLocalOnly SyncPolicy = "local_only"
)

// InstallRecord identifies one immutable installed Skill and its publication policy.
type InstallRecord struct {
	SHA256     string
	Revision   int
	SyncPolicy SyncPolicy
}

// Manifest is the tolerant parse result for one .seed-manifest file.
type Manifest struct {
	Records      map[string]InstallRecord
	RefreshCodes []string
	Warnings     []string
}

// Read loads an installed Skill manifest. A missing file is an empty manifest.
func Read(path string) (*Manifest, error) {
	raw, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return emptyManifest(), nil
	}
	if err != nil {
		return nil, err
	}
	return Parse(raw), nil
}

// Parse tolerantly reads current and legacy manifest records.
func Parse(raw []byte) *Manifest {
	manifest := emptyManifest()
	occurrences := make(map[string]int)
	untrustedCodes := make(map[string]struct{})
	refreshCodes := make(map[string]struct{})
	for lineNumber, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		parts := strings.Split(line, ":")
		name, err := validSkillCode(parts[0])
		if err != nil {
			manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d has invalid skill name", lineNumber+1))
			continue
		}
		occurrences[name]++
		if len(parts) < 2 || len(parts) > 4 {
			manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d has invalid field count", lineNumber+1))
			untrustedCodes[name] = struct{}{}
			continue
		}
		hash, err := normalizedSHA256(parts[1])
		if err != nil {
			manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d has invalid sha256", lineNumber+1))
			untrustedCodes[name] = struct{}{}
			continue
		}
		if len(parts) == 2 {
			manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d uses legacy format", lineNumber+1))
			untrustedCodes[name] = struct{}{}
			refreshCodes[name] = struct{}{}
			continue
		}
		revision, err := strconv.Atoi(strings.TrimSpace(parts[2]))
		if err != nil || revision <= 0 {
			manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d has invalid revision", lineNumber+1))
			untrustedCodes[name] = struct{}{}
			continue
		}
		policy := SyncPolicyPublish
		if len(parts) == 4 {
			policy = SyncPolicy(strings.TrimSpace(parts[3]))
			if !policy.Valid() {
				manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("line %d has invalid sync policy", lineNumber+1))
				untrustedCodes[name] = struct{}{}
				continue
			}
		}
		manifest.Records[name] = InstallRecord{SHA256: hash, Revision: revision, SyncPolicy: policy}
	}
	for name, count := range occurrences {
		if count <= 1 {
			continue
		}
		delete(manifest.Records, name)
		untrustedCodes[name] = struct{}{}
		refreshCodes[name] = struct{}{}
		manifest.Warnings = append(manifest.Warnings, fmt.Sprintf("skill %q has duplicate records", name))
	}
	for name := range untrustedCodes {
		delete(manifest.Records, name)
	}
	manifest.RefreshCodes = make([]string, 0, len(refreshCodes))
	for name := range refreshCodes {
		manifest.RefreshCodes = append(manifest.RefreshCodes, name)
	}
	sort.Strings(manifest.RefreshCodes)
	return manifest
}

// Write atomically persists the current four-field manifest format.
func Write(path string, entries map[string]InstallRecord) error {
	names := make([]string, 0, len(entries))
	for name := range entries {
		names = append(names, name)
	}
	sort.Strings(names)
	var builder strings.Builder
	for _, name := range names {
		entry := entries[name]
		if _, err := validSkillCode(name); err != nil {
			return err
		}
		if _, err := normalizedSHA256(entry.SHA256); err != nil {
			return fmt.Errorf("invalid Skill %q sha256: %w", name, err)
		}
		if entry.Revision <= 0 {
			return fmt.Errorf("invalid Skill %q revision", name)
		}
		if !entry.SyncPolicy.Valid() {
			return fmt.Errorf("invalid Skill %q sync policy %q", name, entry.SyncPolicy)
		}
		fmt.Fprintf(
			&builder,
			"%s:%s:%d:%s\n",
			name,
			strings.ToLower(entry.SHA256),
			entry.Revision,
			entry.SyncPolicy,
		)
	}
	temporary := path + ".tmp"
	if err := os.WriteFile(temporary, []byte(builder.String()), 0o644); err != nil {
		return err
	}
	return os.Rename(temporary, path)
}

// Valid reports whether the sync policy is supported.
func (p SyncPolicy) Valid() bool {
	return p == SyncPolicyPublish || p == SyncPolicyLocalOnly
}

func emptyManifest() *Manifest {
	return &Manifest{Records: make(map[string]InstallRecord)}
}

func validSkillCode(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" || value == "." || value == ".." || filepath.Base(value) != value ||
		strings.ContainsAny(value, `/\`) || strings.HasPrefix(value, ".") ||
		value == "runs" || value == ".system" {
		return "", fmt.Errorf("invalid organization Skill code %q", value)
	}
	return value, nil
}

func normalizedSHA256(value string) (string, error) {
	value = strings.ToLower(strings.TrimSpace(value))
	if len(value) != sha256.Size*2 {
		return "", fmt.Errorf("must be a %d-character hexadecimal value", sha256.Size*2)
	}
	for _, char := range value {
		if !((char >= '0' && char <= '9') || (char >= 'a' && char <= 'f')) {
			return "", fmt.Errorf("must be hexadecimal")
		}
	}
	return value, nil
}
