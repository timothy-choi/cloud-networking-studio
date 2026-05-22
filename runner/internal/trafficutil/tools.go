package trafficutil

import "strings"

const ToolUnavailableMessage = "Required tool is unavailable in this container image. Use Debug Toolbox, choose a different image, or select another check type."

func commandMissing(stderr, tool string) bool {
	s := strings.ToLower(strings.TrimSpace(stderr))
	t := strings.ToLower(strings.TrimSpace(tool))
	if s == "" || t == "" {
		return false
	}
	patterns := []string{
		t + ": not found",
		t + ": applet not found",
		t + ": command not found",
		"executable file not found",
		"no such file or directory",
	}
	for _, p := range patterns {
		if strings.Contains(s, p) && strings.Contains(s, t) {
			return true
		}
	}
	return false
}

func HTTPWgetMissing(stderr string) bool {
	return commandMissing(stderr, "wget")
}

func HTTPCurlMissing(stderr string) bool {
	return commandMissing(stderr, "curl")
}

func PingMissing(stderr string) bool {
	return commandMissing(stderr, "ping")
}

func NcMissing(stderr string) bool {
	return commandMissing(stderr, "nc")
}

func DigMissing(stderr string) bool {
	return commandMissing(stderr, "dig")
}

func AnyToolMissing(stderr string, tools ...string) bool {
	for _, t := range tools {
		if commandMissing(stderr, t) {
			return true
		}
	}
	return false
}
