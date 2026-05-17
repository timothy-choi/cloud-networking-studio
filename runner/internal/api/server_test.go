package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealth(t *testing.T) {
	s := &Server{cli: nil}
	// health handler does not use docker client
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var body map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" {
		t.Fatalf("body %+v", body)
	}
}

func TestRuntimeStatusNilClient(t *testing.T) {
	s := &Server{cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/runtime/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var st struct {
		Status            string `json:"status"`
		DockerReachable   bool   `json:"docker_reachable"`
		RuntimeProvider   string `json:"runtime_provider"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.Status != "degraded" || st.DockerReachable || st.RuntimeProvider != "docker" {
		t.Fatalf("unexpected %+v", st)
	}
}

func TestPostDeploymentInvalidJSON(t *testing.T) {
	s := &Server{cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments", s.handlePostDeployment)
	req := httptest.NewRequest(http.MethodPost, "/deployments", strings.NewReader("not-json"))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400 got %d body=%q", rec.Code, rec.Body.String())
	}
}

func TestPostDeploymentSegmentedRejected(t *testing.T) {
	s := &Server{cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments", s.handlePostDeployment)
	body := `{"deployment_id":"d","topology_id":"550e8400-e29b-41d4-a716-446655440000","runtime_target":"docker","networking_mode":"bridge","segmented_networks":true,"nodes":[]}`
	req := httptest.NewRequest(http.MethodPost, "/deployments", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400 got %d", rec.Code)
	}
}
