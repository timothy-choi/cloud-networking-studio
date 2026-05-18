package trafficutil

import "strings"

// HTTPWgetMissing reports stderr that indicates wget is not available in the source workload image.
func HTTPWgetMissing(stderr string) bool {
	s := strings.ToLower(strings.TrimSpace(stderr))
	if s == "" {
		return false
	}
	if strings.Contains(s, "wget: not found") {
		return true
	}
	if strings.Contains(s, "wget: applet not found") {
		return true
	}
	if strings.Contains(s, "wget: command not found") {
		return true
	}
	if strings.Contains(s, "executable file not found") && strings.Contains(s, "wget") {
		return true
	}
	if strings.Contains(s, "no such file or directory") && strings.Contains(s, "wget") {
		return true
	}
	return false
}
