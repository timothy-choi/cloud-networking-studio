package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWithRequestIdLoggingReadsHeader(t *testing.T) {
	var seen string
	h := withRequestIdLogging(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = strings.TrimSpace(r.Header.Get("X-Request-ID"))
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodPost, "/deployments", nil)
	req.Header.Set("X-Request-ID", "test-rid-123")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d", rec.Code)
	}
	if seen != "test-rid-123" {
		t.Fatalf("expected request id on inner handler, got %q", seen)
	}
}
