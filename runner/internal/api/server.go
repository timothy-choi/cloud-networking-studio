package api

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"time"

	docker "github.com/fsouza/go-dockerclient"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	rdocker "github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/docker"
)

// Server exposes the Go runner HTTP API.
type Server struct {
	cli *docker.Client
}

func NewServer() (*Server, error) {
	cli, err := rdocker.NewClient()
	if err != nil {
		return nil, err
	}
	return &Server{cli: cli}, nil
}

// Handler returns the root HTTP handler.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	mux.HandleFunc("POST /deployments", s.handlePostDeployment)
	mux.HandleFunc("DELETE /deployments/{id}", s.handleDeleteDeploymentID)
	mux.HandleFunc("GET /deployments/{id}/logs", s.handleDeploymentLogs)
	mux.HandleFunc("GET /deployments/{id}", s.handleGetDeploymentID)
	mux.HandleFunc("POST /traffic-tests", s.handleTraffic)
	return mux
}

func (s *Server) ctx(r *http.Request) (context.Context, context.CancelFunc) {
	return context.WithTimeout(r.Context(), 10*time.Minute)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "cns-runner"})
}

func (s *Server) handleRuntimeStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	if s.cli == nil {
		st := model.RuntimeStatus{
			RuntimeProvider: "docker",
			DockerReachable: false,
			Status:          "degraded",
			Message:         "docker client not initialized",
		}
		_ = ctx
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(st)
		return
	}
	_, err := s.cli.Info()
	st := model.RuntimeStatus{RuntimeProvider: "docker", DockerReachable: err == nil, Status: "ok"}
	if err != nil {
		st.Status = "degraded"
		st.Message = err.Error()
	}
	_ = ctx
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(st)
}

func (s *Server) handlePostDeployment(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req model.DeploymentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	resp := rdocker.DeploySimple(ctx, s.cli, &req)
	status := http.StatusOK
	if resp.Error != nil {
		status = http.StatusBadRequest
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(resp)
}

func (s *Server) handleDeleteDeploymentID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	topologyID := r.URL.Query().Get("topology_id")
	if topologyID == "" {
		http.Error(w, "topology_id query parameter is required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	events := rdocker.DestroyTopology(ctx, s.cli, topologyID)
	resp := model.DeploymentResponse{Status: "succeeded", RuntimeProvider: "docker"}
	for _, e := range events {
		resp.Events = append(resp.Events, e)
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
	_ = deploymentID
}

func (s *Server) handleGetDeploymentID(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	topologyID := r.URL.Query().Get("topology_id")
	if topologyID == "" {
		http.Error(w, "topology_id query parameter is required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	ctrs, err := s.cli.ListContainers(docker.ListContainersOptions{
		Context: ctx,
		All:     true,
		Filters: map[string][]string{"label": {"cns.topology_id=" + topologyID}},
	})
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	ids := make([]string, 0, len(ctrs))
	for _, c := range ctrs {
		ids = append(ids, c.ID)
	}
	out := model.DeploymentGetResponse{
		DeploymentID:    deploymentID,
		TopologyID:      topologyID,
		Status:          "active",
		RuntimeProvider: "docker",
		ContainerIDs:    ids,
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(out)
}

func (s *Server) handleDeploymentLogs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	nodeID := r.URL.Query().Get("node_id")
	topologyID := r.URL.Query().Get("topology_id")
	tail, _ := strconv.Atoi(r.URL.Query().Get("tail"))
	if nodeID == "" || topologyID == "" {
		http.Error(w, "node_id and topology_id query parameters are required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	logs, err := rdocker.LogsForNode(ctx, s.cli, topologyID, nodeID, tail)
	if err != nil {
		msg := err.Error()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(model.LogsResponse{DeploymentID: deploymentID, NodeID: nodeID, Error: &msg})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(model.LogsResponse{DeploymentID: deploymentID, NodeID: nodeID, Logs: logs})
}

func (s *Server) handleTraffic(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req model.TrafficRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	resp := rdocker.RunTrafficTest(ctx, s.cli, &req)
	code := http.StatusOK
	if !resp.Success && resp.Error != nil {
		code = http.StatusBadRequest
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(resp)
}
