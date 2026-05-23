package kubernetes

import (
	"regexp"
	"strings"
)

var dnsLabel = regexp.MustCompile(`[^a-z0-9-]+`)

// short8 strips hyphens from a UUID-like string and returns up to 8 lowercase hex chars (padded).
func short8(id string) string {
	s := strings.ReplaceAll(strings.TrimSpace(strings.ToLower(id)), "-", "")
	if len(s) < 8 {
		if s == "" {
			return "00000000"
		}
		return s + strings.Repeat("0", 8-len(s))
	}
	return s[:8]
}

// NamespaceFor builds a deterministic namespace name per deployment (RFC 1123, max 63 chars).
// Pattern: cns-deploy-{first 8 hex of deployment UUID}.
func NamespaceFor(projectID, topologyID, deploymentID string) string {
	_ = projectID
	_ = topologyID
	raw := "cns-deploy-" + short8(deploymentID)
	return sanitizeRFC1123Label(raw)
}

func sanitizeRFC1123Label(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	s = dnsLabel.ReplaceAllString(s, "-")
	s = strings.Trim(s, "-")
	for strings.Contains(s, "--") {
		s = strings.ReplaceAll(s, "--", "-")
	}
	if len(s) > 63 {
		s = s[:63]
	}
	s = strings.Trim(s, "-")
	if s == "" {
		s = "cns-default"
	}
	return s
}
