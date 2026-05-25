package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"k8s.io/client-go/kubernetes/fake"
	"k8s.io/client-go/rest"
)

func TestHealth(t *testing.T) {
	s := &Server{cli: nil}
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
	if body["status"] != "ok" || body["runner_status"] != "ok" {
		t.Fatalf("body %+v", body)
	}
}

func TestVersion(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /version", s.handleVersion)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/version", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var body struct {
		Service string `json:"service"`
		Version string `json:"version"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Service != "cns-runner" || body.Version == "" {
		t.Fatalf("unexpected %+v", body)
	}
}

func TestStatusSupportedOperations(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /status", s.handleStatus)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var st struct {
		RunnerStatus        string   `json:"runner_status"`
		SupportedOperations []string `json:"supported_operations"`
		Version             string   `json:"version"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.RunnerStatus != "degraded" {
		t.Fatalf("runner_status %+v", st)
	}
	want := map[string]bool{
		"deploy": true, "destroy": true, "logs": true, "exec": true,
		"health_check": true, "traffic_test": true, "terminal": true,
		"infra_terraform": true, "infra_ansible": true,
	}
	for _, op := range st.SupportedOperations {
		if !want[op] {
			t.Fatalf("unexpected op %q in %+v", op, st.SupportedOperations)
		}
		delete(want, op)
	}
	if len(want) != 0 {
		t.Fatalf("missing ops %+v got %+v", want, st.SupportedOperations)
	}
	if st.Version == "" {
		t.Fatalf("version missing")
	}
}

func TestRuntimeStatusNilClient(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/runtime/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var st struct {
		Status                 string `json:"status"`
		DockerReachable        bool   `json:"docker_reachable"`
		KubernetesReachable    bool   `json:"kubernetes_reachable"`
		RuntimeProvider        string `json:"runtime_provider"`
		CurrentContext         string `json:"current_context"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.Status != "degraded" || st.DockerReachable || st.RuntimeProvider != "docker" {
		t.Fatalf("unexpected %+v", st)
	}
	if st.KubernetesReachable {
		t.Fatalf("kubernetes should be false for docker-only server %+v", st)
	}
	if st.CurrentContext != "" {
		t.Fatalf("unexpected context %q", st.CurrentContext)
	}
}

func TestRuntimeStatusKubernetesInitError(t *testing.T) {
	s := &Server{
		provider:          "kubernetes",
		k8sCtx:            "kind-test",
		kubeconfigSource:  "/tmp/missing-kubeconfig",
		kubernetesInitErr: "kubeconfig not found",
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/runtime/status", nil))
	var st struct {
		Status              string `json:"status"`
		KubernetesReachable bool   `json:"kubernetes_reachable"`
		KubernetesInitError string `json:"kubernetes_init_error"`
		KubeconfigSource    string `json:"kubeconfig_source"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.Status != "degraded" || st.KubernetesReachable || st.KubernetesInitError == "" {
		t.Fatalf("unexpected %+v", st)
	}
	if st.KubeconfigSource != "/tmp/missing-kubeconfig" {
		t.Fatalf("source %+v", st)
	}
}

func TestRuntimeStatusKubernetesFakeClient(t *testing.T) {
	cs := fake.NewSimpleClientset()
	s := &Server{
		provider: "kubernetes",
		k8s:      cs,
		k8sCfg:   &rest.Config{Host: "http://127.0.0.1:1"},
		k8sCtx:   "kind-kind",
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/runtime/status", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d", rec.Code)
	}
	var st struct {
		Status                 string `json:"status"`
		RuntimeProvider        string `json:"runtime_provider"`
		KubernetesReachable    bool   `json:"kubernetes_reachable"`
		DockerReachable        bool   `json:"docker_reachable"`
		CurrentContext         string `json:"current_context"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &st); err != nil {
		t.Fatal(err)
	}
	if st.RuntimeProvider != "kubernetes" || !st.KubernetesReachable || st.DockerReachable {
		t.Fatalf("unexpected %+v", st)
	}
	if st.CurrentContext != "kind-kind" {
		t.Fatalf("context %q", st.CurrentContext)
	}
	if st.Status != "ok" {
		t.Fatalf("status %q", st.Status)
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

func TestRuntimeDeploymentLogsDockerNilClient(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /deployments/{id}/runtime/logs", s.handleRuntimeDeploymentLogs)
	req := httptest.NewRequest(http.MethodGet, "/deployments/did/runtime/logs?topology_id=550e8400-e29b-41d4-a716-446655440000", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503 got %d body=%q", rec.Code, rec.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["runtime_provider"] != "docker" {
		t.Fatalf("body %+v", body)
	}
}

func TestRuntimeHealthResponseShape(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/health-check", s.handleRuntimeServiceHealth)
	req := httptest.NewRequest(
		http.MethodPost,
		"/deployments/did/runtime/services/nid/health-check?topology_id=t1",
		strings.NewReader(`{"port":80,"path":"/"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503 got %d", rec.Code)
	}
	var body struct {
		Status    string `json:"status"`
		Target    string `json:"target"`
		LatencyMs *int64 `json:"latency_ms"`
		Message   string `json:"message"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "failed" || body.Message == "" || body.LatencyMs == nil {
		t.Fatalf("unexpected %+v", body)
	}
}

func TestRuntimeServiceLogsKubernetesFake(t *testing.T) {
	cs := fake.NewSimpleClientset()
	s := &Server{
		provider: "kubernetes",
		k8s:      cs,
		k8sCfg:   &rest.Config{Host: "http://127.0.0.1:1"},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /deployments/{id}/runtime/services/{service_id}/logs", s.handleRuntimeServiceLogs)
	req := httptest.NewRequest(
		http.MethodGet,
		"/deployments/did/runtime/services/n1/logs?topology_id=t1&project_id=p1",
		nil,
	)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("want 404 got %d %s", rec.Code, rec.Body.String())
	}
}

func TestRuntimeServiceExecRejectedJSON(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/exec", s.handleRuntimeServiceExec)
	req := httptest.NewRequest(
		http.MethodPost,
		"/deployments/did/runtime/services/nid/exec?topology_id=t1",
		strings.NewReader(`{"command":"rm -f /","timeout_seconds":10}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200 got %d %s", rec.Code, rec.Body.String())
	}
	var body struct {
		Status  string `json:"status"`
		Message string `json:"message"`
		Command string `json:"command"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "rejected" || body.Message == "" || body.Command == "" {
		t.Fatalf("unexpected %+v", body)
	}
}

func TestRuntimeServiceExecDockerNilClientUnsupported(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/exec", s.handleRuntimeServiceExec)
	req := httptest.NewRequest(
		http.MethodPost,
		"/deployments/did/runtime/services/nid/exec?topology_id=t1",
		strings.NewReader(`{"command":"whoami","timeout_seconds":10}`),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("want 200 got %d %s", rec.Code, rec.Body.String())
	}
	var body struct {
		Status  string `json:"status"`
		Message string `json:"message"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "unsupported" {
		t.Fatalf("unexpected %+v", body)
	}
}

func TestRuntimeServiceRestartDockerNilClient503(t *testing.T) {
	s := &Server{provider: "docker", cli: nil}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/restart", s.handleRuntimeServiceRestart)
	req := httptest.NewRequest(
		http.MethodPost,
		"/deployments/did/runtime/services/nid/restart?topology_id=t1",
		nil,
	)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503 got %d %s", rec.Code, rec.Body.String())
	}
}

func TestRuntimeServiceRestartKubernetesNilClient503(t *testing.T) {
	s := &Server{provider: "kubernetes", k8s: nil, k8sCfg: &rest.Config{Host: "http://127.0.0.1:1"}}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/restart", s.handleRuntimeServiceRestart)
	req := httptest.NewRequest(
		http.MethodPost,
		"/deployments/did/runtime/services/nid/restart?topology_id=t1",
		nil,
	)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("want 503 got %d %s", rec.Code, rec.Body.String())
	}
}
