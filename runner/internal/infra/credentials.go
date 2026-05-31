package infra

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

var executionIDSanitizer = regexp.MustCompile(`[^a-zA-Z0-9-]+`)

// prepareTerraformCredentialEnv merges request credentials into the process environment.
// Inline GOOGLE_CREDENTIALS_JSON from credential profiles is written to a runner-local
// temp file and exposed as GOOGLE_APPLICATION_CREDENTIALS for the Terraform subprocess.
func prepareTerraformCredentialEnv(credentialsEnv map[string]string, executionID string) ([]string, func(), error) {
	cleanup := func() {}
	env := append([]string{}, os.Environ()...)
	if len(credentialsEnv) == 0 {
		return env, cleanup, nil
	}

	inlineJSON := strings.TrimSpace(credentialsEnv["GOOGLE_CREDENTIALS_JSON"])
	if inlineJSON != "" {
		path := filepath.Join(os.TempDir(), fmt.Sprintf("cns-gcp-sa-%s.json", sanitizeExecutionID(executionID)))
		if err := os.WriteFile(path, []byte(inlineJSON), 0o600); err != nil {
			return nil, cleanup, fmt.Errorf("failed to write GCP credential temp file: %w", err)
		}
		if _, statErr := os.Stat(path); statErr != nil {
			return nil, cleanup, fmt.Errorf("GCP credential temp file missing after write: %w", statErr)
		}
		log.Printf("[infra] credential temp file=%s exists before terraform invocation", path)
		cleanup = func() {
			if rmErr := os.Remove(path); rmErr != nil {
				log.Printf("[infra] credential temp file cleanup failed path=%s err=%v", path, rmErr)
				return
			}
			log.Printf("[infra] credential temp file removed path=%s", path)
		}
		for k, v := range credentialsEnv {
			if k == "GOOGLE_CREDENTIALS_JSON" {
				continue
			}
			env = append(env, fmt.Sprintf("%s=%s", k, v))
		}
		env = append(env, "GOOGLE_APPLICATION_CREDENTIALS="+path)
		return env, cleanup, nil
	}

	for k, v := range credentialsEnv {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}
	if path := strings.TrimSpace(credentialsEnv["GOOGLE_APPLICATION_CREDENTIALS"]); path != "" {
		_, statErr := os.Stat(path)
		log.Printf("[infra] credential path=%s exists=%v", path, statErr == nil)
	}
	return env, cleanup, nil
}

func sanitizeExecutionID(executionID string) string {
	safe := executionIDSanitizer.ReplaceAllString(strings.TrimSpace(executionID), "")
	if safe == "" {
		safe = "exec"
	}
	if len(safe) > 48 {
		safe = safe[:48]
	}
	return safe
}
