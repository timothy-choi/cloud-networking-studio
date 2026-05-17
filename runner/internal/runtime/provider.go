package runtime

import (
	"os"
	"strings"
)

// RuntimeProviderEnv returns RUNTIME_PROVIDER: "docker" (default) or "kubernetes".
// Unknown values fall back to "docker" so optional misconfiguration never disables the stack.
func RuntimeProviderEnv() string {
	v := strings.TrimSpace(strings.ToLower(os.Getenv("RUNTIME_PROVIDER")))
	switch v {
	case "", "docker":
		return "docker"
	case "k8s", "kubernetes":
		return "kubernetes"
	default:
		return "docker"
	}
}
