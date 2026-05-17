package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/safeexec"
	rdocker "github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/docker"
	rk8s "github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/kubernetes"
)

func intPtrExec(i int) *int { return &i }

func (s *Server) handleRuntimeServiceExec(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	nodeID := strings.TrimSpace(r.PathValue("service_id"))
	topologyID := strings.TrimSpace(r.URL.Query().Get("topology_id"))
	projectID := strings.TrimSpace(r.URL.Query().Get("project_id"))
	if nodeID == "" || topologyID == "" {
		http.Error(w, "service_id path and topology_id query parameter are required", http.StatusBadRequest)
		return
	}
	var req model.RuntimeExecRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	cmd := strings.TrimSpace(req.Command)
	started := time.Now().UTC().Format(time.RFC3339Nano)
	prov := "docker"
	if s.useKubernetes() {
		prov = "kubernetes"
	}

	argv, vErr := safeexec.Validate(cmd)
	if vErr != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(model.RuntimeExecResponse{
			DeploymentID:    deploymentID,
			ServiceID:       nodeID,
			Command:         cmd,
			Status:          "rejected",
			Message:         vErr.Error(),
			StartedAt:       started,
			FinishedAt:      time.Now().UTC().Format(time.RFC3339Nano),
			RuntimeProvider: prov,
		})
		return
	}

	sec := req.TimeoutSeconds
	if sec <= 0 {
		sec = 30
	}
	if sec > 120 {
		sec = 120
	}
	timeout := time.Duration(sec) * time.Second
	ctx, cancel := s.ctx(r)
	defer cancel()

	var stdout, stderr string
	var exitCode int
	var st string

	if s.useKubernetes() {
		if s.k8s == nil || s.k8sCfg == nil {
			writeExecUnsupported(w, deploymentID, nodeID, cmd, started, prov, "kubernetes client not initialized")
			return
		}
		stdout, stderr, exitCode, st = rk8s.SafeExecWorkload(ctx, s.k8sCfg, s.k8s, topologyID, deploymentID, projectID, nodeID, argv, timeout)
	} else {
		if s.cli == nil {
			writeExecUnsupported(w, deploymentID, nodeID, cmd, started, prov, "docker client not initialized")
			return
		}
		stdout, stderr, exitCode, st = rdocker.SafeExecWorkload(ctx, s.cli, topologyID, nodeID, argv, timeout)
	}

	finished := time.Now().UTC().Format(time.RFC3339Nano)
	resp := model.RuntimeExecResponse{
		DeploymentID:    deploymentID,
		ServiceID:       nodeID,
		Command:         cmd,
		Status:          st,
		Stdout:          stdout,
		Stderr:          stderr,
		StartedAt:       started,
		FinishedAt:      finished,
		RuntimeProvider: prov,
		ExitCode:        intPtrExec(exitCode),
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(resp)
}

func writeExecUnsupported(w http.ResponseWriter, deploymentID, nodeID, cmd, started, prov, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(model.RuntimeExecResponse{
		DeploymentID:    deploymentID,
		ServiceID:       nodeID,
		Command:         cmd,
		Status:          "unsupported",
		Message:         msg,
		StartedAt:       started,
		FinishedAt:      time.Now().UTC().Format(time.RFC3339Nano),
		RuntimeProvider: prov,
	})
}

func (s *Server) handleRuntimeServiceRestart(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	nodeID := strings.TrimSpace(r.PathValue("service_id"))
	topologyID := strings.TrimSpace(r.URL.Query().Get("topology_id"))
	projectID := strings.TrimSpace(r.URL.Query().Get("project_id"))
	if nodeID == "" || topologyID == "" {
		http.Error(w, "service_id path and topology_id query parameter are required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()

	prov := "docker"
	if s.useKubernetes() {
		prov = "kubernetes"
	}
	out := model.RuntimeRestartResponse{RuntimeProvider: prov}

	if s.useKubernetes() {
		if s.k8s == nil {
			out.Status = "failed"
			out.Message = "kubernetes client not initialized"
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(out)
			return
		}
		if err := rk8s.RestartWorkload(ctx, s.k8s, topologyID, deploymentID, projectID, nodeID); err != nil {
			out.Status = "failed"
			out.Message = err.Error()
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_ = json.NewEncoder(w).Encode(out)
			return
		}
		out.Status = "succeeded"
		out.Message = "pod deleted; deployment should recreate it"
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
		return
	}

	if s.cli == nil {
		out.Status = "failed"
		out.Message = "docker client not initialized"
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_ = json.NewEncoder(w).Encode(out)
		return
	}
	if err := rdocker.RestartWorkload(ctx, s.cli, topologyID, nodeID); err != nil {
		out.Status = "failed"
		out.Message = err.Error()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
		return
	}
	out.Status = "succeeded"
	out.Message = "container restarted"
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}
