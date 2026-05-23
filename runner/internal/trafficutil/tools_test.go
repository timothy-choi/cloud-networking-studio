package trafficutil

import "testing"

func TestToolUnavailableMessageConstant(t *testing.T) {
	if ToolUnavailableMessage == "" {
		t.Fatal("expected message")
	}
}

func TestPingMissingDetectsNotFound(t *testing.T) {
	stderr := "ping: not found"
	if !PingMissing(stderr) {
		t.Fatal("expected ping missing")
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
