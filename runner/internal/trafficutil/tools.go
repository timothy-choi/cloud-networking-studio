package trafficutil

import "strings"

const ToolUnavailableMessage = "Tool missing in this image. Use Debug Toolbox or install tools with a bootstrap command."

const NoHTTPServiceMessage = "No HTTP service appears to be running. Configure a server command or use runtime/TCP check."

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

func IpMissing(stderr string) bool {
	return commandMissing(stderr, "ip")
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

func HTTPConnectionRefused(combined string) bool {
	s := strings.ToLower(strings.TrimSpace(combined))
	if s == "" {
		return false
	}
	patterns := []string{
		"connection refused",
		"failed to connect",
		"couldn't connect to server",
		"could not connect to server",
		"unable to connect",
		"can't connect",
		"connection reset by peer",
		"no route to host",
	}
	for _, p := range patterns {
		if strings.Contains(s, p) {
			return true
		}
	}
	return false
}

// ExecArgvToolMissing reports whether argv[0] appears missing from exec output.
func ExecArgvToolMissing(argv []string, combined string) bool {
	if len(argv) == 0 {
		return false
	}
	tool := argv[0]
	switch tool {
	case "ip":
		return IpMissing(combined) || AnyToolMissing(combined, "ip")
	case "ping":
		return PingMissing(combined)
	case "curl":
		return HTTPCurlMissing(combined)
	case "wget":
		return HTTPWgetMissing(combined)
	case "nslookup":
		return AnyToolMissing(combined, "nslookup", "dig")
	default:
		return AnyToolMissing(combined, tool)
	}
}
