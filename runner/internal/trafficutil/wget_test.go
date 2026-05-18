package trafficutil

import "testing"

func TestHTTPWgetMissing(t *testing.T) {
	if !HTTPWgetMissing("/bin/sh: wget: not found") {
		t.Fatal("expected alpine-style missing wget")
	}
	if !HTTPWgetMissing("wget: not found") {
		t.Fatal("expected bare message")
	}
	if HTTPWgetMissing("connection refused") {
		t.Fatal("should not match network errors")
	}
}
