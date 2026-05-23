package trafficutil

import (
	"strings"
	"testing"
)

func TestToolUnavailableMessageConstant(t *testing.T) {
	if ToolUnavailableMessage == "" {
		t.Fatal("expected message")
	}
	if !containsAll(ToolUnavailableMessage, "Tool missing", "Debug Toolbox", "bootstrap command") {
		t.Fatalf("unexpected message: %q", ToolUnavailableMessage)
	}
}

func TestNoHTTPServiceMessageConstant(t *testing.T) {
	if NoHTTPServiceMessage == "" {
		t.Fatal("expected message")
	}
}

func TestPingMissingDetectsNotFound(t *testing.T) {
	stderr := "ping: not found"
	if !PingMissing(stderr) {
		t.Fatal("expected ping missing")
	}
}

func TestIpMissingDetectsNotFound(t *testing.T) {
	stderr := "ip: not found"
	if !IpMissing(stderr) {
		t.Fatal("expected ip missing")
	}
}

func TestHTTPWgetMissingDetectsNotFound(t *testing.T) {
	stderr := "wget: not found"
	if !HTTPWgetMissing(stderr) {
		t.Fatal("expected wget missing")
	}
}

func TestNcMissingDetectsNotFound(t *testing.T) {
	stderr := "nc: not found"
	if !NcMissing(stderr) {
		t.Fatal("expected nc missing")
	}
}

func TestHTTPConnectionRefused(t *testing.T) {
	if !HTTPConnectionRefused("wget: unable to connect to host: Connection refused") {
		t.Fatal("expected connection refused")
	}
}

func TestExecArgvToolMissing(t *testing.T) {
	if !ExecArgvToolMissing([]string{"ip", "addr"}, "ip: not found") {
		t.Fatal("expected ip exec missing")
	}
	if !ExecArgvToolMissing([]string{"ping", "1.2.3.4"}, "ping: not found") {
		t.Fatal("expected ping exec missing")
	}
}

func containsAll(s string, parts ...string) bool {
	for _, p := range parts {
		if !strings.Contains(s, p) {
			return false
		}
	}
	return true
}
