// Package safeexec validates one-line diagnostic commands for runtime exec.
package safeexec

import (
	"fmt"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

var psArgPattern = regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)
var hostTokenPattern = regexp.MustCompile(`^[a-zA-Z0-9._-]+$`)

var forbiddenRunes = []rune{';', '&', '|', '`', '$', '>', '<', '\n', '\r'}

var dangerousSubstrings = []string{
	"rm ", " rm", "/rm", "shutdown", "reboot", "mkfs", " dd ", "dd ", "/dd",
	"chmod", "chown", "apt-get", "apt ", "yum ", "dnf ", "apk ", "pip ", "npm ",
	"curl |", "wget |", "sh -", "bash ", "/bin/sh", "/bin/bash",
}

// Validate parses and validates a single-line command; returns argv for exec or an error message.
func Validate(raw string) ([]string, error) {
	s := strings.TrimSpace(raw)
	if s == "" {
		return nil, fmt.Errorf("empty command")
	}
	for _, ch := range forbiddenRunes {
		if strings.ContainsRune(s, ch) {
			return nil, fmt.Errorf("command is not allowed in safe exec mode")
		}
	}
	low := strings.ToLower(s)
	for _, d := range dangerousSubstrings {
		if strings.Contains(low, d) {
			return nil, fmt.Errorf("command is not allowed in safe exec mode")
		}
	}
	fields := strings.Fields(s)
	if len(fields) == 0 {
		return nil, fmt.Errorf("empty command")
	}
	if strings.EqualFold(fields[0], "rm") {
		return nil, fmt.Errorf("command is not allowed in safe exec mode")
	}
	switch fields[0] {
	case "whoami":
		if len(fields) != 1 {
			return nil, fmt.Errorf("whoami takes no arguments")
		}
		return fields, nil
	case "hostname":
		if len(fields) == 1 {
			return fields, nil
		}
		if len(fields) == 2 && fields[1] == "-f" {
			return fields, nil
		}
		return nil, fmt.Errorf("hostname: only optional -f allowed")
	case "env":
		if len(fields) != 1 {
			return nil, fmt.Errorf("env takes no arguments")
		}
		return fields, nil
	case "ps":
		if len(fields) < 1 {
			return nil, fmt.Errorf("invalid ps")
		}
		for i := 1; i < len(fields); i++ {
			if !psArgPattern.MatchString(fields[i]) {
				return nil, fmt.Errorf("ps: disallowed argument %q", fields[i])
			}
		}
		return fields, nil
	case "ip":
		if len(fields) < 2 {
			return nil, fmt.Errorf("ip: need subcommand")
		}
		switch fields[1] {
		case "addr":
			if len(fields) != 2 {
				return nil, fmt.Errorf("ip addr takes no extra args")
			}
		case "route":
			if len(fields) == 2 {
				return fields, nil
			}
			if len(fields) == 3 && fields[2] == "show" {
				return fields, nil
			}
			return nil, fmt.Errorf("ip route: only optional 'show'")
		default:
			return nil, fmt.Errorf("ip: only addr or route allowed")
		}
		return fields, nil
	case "cat":
		if len(fields) != 2 || fields[1] != "/etc/resolv.conf" {
			return nil, fmt.Errorf("cat: only /etc/resolv.conf allowed")
		}
		return fields, nil
	case "nslookup":
		if len(fields) != 2 {
			return nil, fmt.Errorf("nslookup: exactly one target required")
		}
		if !safeHostToken(fields[1]) {
			return nil, fmt.Errorf("nslookup: invalid target")
		}
		return fields, nil
	case "curl":
		if len(fields) != 2 {
			return nil, fmt.Errorf("curl: exactly one URL required")
		}
		if err := validateHTTPURL(fields[1]); err != nil {
			return nil, err
		}
		return fields, nil
	case "wget":
		if len(fields) != 2 {
			return nil, fmt.Errorf("wget: exactly one URL required")
		}
		if err := validateHTTPURL(fields[1]); err != nil {
			return nil, err
		}
		return fields, nil
	case "ping":
		if len(fields) == 2 {
			if !safeHostToken(fields[1]) {
				return nil, fmt.Errorf("ping: invalid target")
			}
			return []string{"ping", "-c", "3", fields[1]}, nil
		}
		if len(fields) == 4 && fields[1] == "-c" {
			n, err := strconv.Atoi(fields[2])
			if err != nil || n < 1 || n > 10 {
				return nil, fmt.Errorf("ping: count must be 1-10")
			}
			if !safeHostToken(fields[3]) {
				return nil, fmt.Errorf("ping: invalid target")
			}
			return fields, nil
		}
		return nil, fmt.Errorf("ping: use 'ping <host>' or 'ping -c N <host>' (N 1-10)")
	default:
		return nil, fmt.Errorf("command is not allowed in safe exec mode")
	}
}

func safeHostToken(s string) bool {
	if len(s) == 0 || len(s) > 253 {
		return false
	}
	return hostTokenPattern.MatchString(s)
}

func validateHTTPURL(s string) error {
	u, err := url.Parse(s)
	if err != nil {
		return fmt.Errorf("curl/wget: invalid URL")
	}
	if (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return fmt.Errorf("curl/wget: URL must be http(s) with host")
	}
	if strings.ContainsAny(s, " \t") {
		return fmt.Errorf("curl/wget: URL must be a single token")
	}
	return nil
}
