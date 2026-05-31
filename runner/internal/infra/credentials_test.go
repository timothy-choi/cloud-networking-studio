package infra

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPrepareTerraformCredentialEnv_InlineJSONMaterializesTempFile(t *testing.T) {
	t.Parallel()
	inline := `{"type":"service_account","project_id":"demo","private_key":"x","client_email":"a@b.c"}`
	env, cleanup, err := prepareTerraformCredentialEnv(map[string]string{
		"GOOGLE_CREDENTIALS_JSON": inline,
	}, "exec-plan-1")
	if err != nil {
		t.Fatalf("prepareTerraformCredentialEnv: %v", err)
	}
	defer cleanup()

	path := credentialPathFromEnv(t, env)
	if _, statErr := os.Stat(path); statErr != nil {
		t.Fatalf("expected temp credential file before cleanup: %v", statErr)
	}
	data, readErr := os.ReadFile(path)
	if readErr != nil {
		t.Fatalf("read temp credential file: %v", readErr)
	}
	if string(data) != inline {
		t.Fatalf("unexpected credential file contents: %q", string(data))
	}
	if envValue(env, "GOOGLE_CREDENTIALS_JSON") != "" {
		t.Fatalf("GOOGLE_CREDENTIALS_JSON should not be passed to terraform subprocess")
	}

	cleanup()
	if _, statErr := os.Stat(path); !os.IsNotExist(statErr) {
		t.Fatalf("expected temp credential file removed after cleanup, stat err=%v", statErr)
	}
}

func TestPrepareTerraformCredentialEnv_InlineJSONCleanupAfterFailure(t *testing.T) {
	t.Parallel()
	env, cleanup, err := prepareTerraformCredentialEnv(map[string]string{
		"GOOGLE_CREDENTIALS_JSON": `{"type":"service_account","project_id":"demo"}`,
	}, "exec-fail-1")
	if err != nil {
		t.Fatalf("prepareTerraformCredentialEnv: %v", err)
	}
	path := credentialPathFromEnv(t, env)
	cleanup()
	if _, statErr := os.Stat(path); !os.IsNotExist(statErr) {
		t.Fatalf("expected temp credential file removed after failure cleanup, stat err=%v", statErr)
	}
}

func TestPrepareTerraformCredentialEnv_FilePathPassthrough(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	path := filepath.Join(dir, "gcp-sa.json")
	if err := os.WriteFile(path, []byte(`{"type":"service_account"}`), 0o600); err != nil {
		t.Fatalf("write fixture: %v", err)
	}
	env, cleanup, err := prepareTerraformCredentialEnv(map[string]string{
		"GOOGLE_APPLICATION_CREDENTIALS": path,
	}, "exec-file-1")
	if err != nil {
		t.Fatalf("prepareTerraformCredentialEnv: %v", err)
	}
	defer cleanup()
	if got := envValue(env, "GOOGLE_APPLICATION_CREDENTIALS"); got != path {
		t.Fatalf("expected passthrough path %q, got %q", path, got)
	}
}

func credentialPathFromEnv(t *testing.T, env []string) string {
	t.Helper()
	path := envValue(env, "GOOGLE_APPLICATION_CREDENTIALS")
	if path == "" {
		t.Fatal("GOOGLE_APPLICATION_CREDENTIALS missing from env")
	}
	return path
}

func envValue(env []string, key string) string {
	prefix := key + "="
	for _, item := range env {
		if strings.HasPrefix(item, prefix) {
			return strings.TrimPrefix(item, prefix)
		}
	}
	return ""
}
