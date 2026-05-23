package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	docker "github.com/fsouza/go-dockerclient"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime"
	rdocker "github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/docker"
	rk8s "github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/kubernetes"
)

// Server exposes the Go runner HTTP API.
type Server struct {
	provider           string
	cli                *docker.Client
	k8s                kubernetes.Interface
	k8sCfg             *rest.Config
	k8sCtx             string
	kubeconfigSource   string
	kubernetesInitErr  string
}

func NewServer() (*Server, error) {
	prov := runtime.RuntimeProviderEnv()
	s := &Server{provider: prov}
	switch prov {
	case "kubernetes":
		cs, cfg, meta, err := rk8s.NewClientsetWithMeta()
		s.k8sCtx = meta.Context
		s.kubeconfigSource = meta.Source
		if err != nil {
			s.kubernetesInitErr = err.Error()
			break
		}
		if msg := rk8s.ProductionBlocked(meta, os.Getenv("CNS_ENVIRONMENT")); msg != "" {
			s.kubernetesInitErr = msg
			break
		}
		s.k8s, s.k8sCfg = cs, cfg
	default:
		cli, err := rdocker.NewClient()
		if err != nil {
			return nil, fmt.Errorf("runner docker client: %w", err)
		}
		s.cli = cli
	}
	// Optional docker probe for status diagnostics (even when primary provider is kubernetes).
	if s.cli == nil {
		if cli, err := rdocker.NewClient(); err == nil {
			s.cli = cli
		}
	}
	return s, nil
}

func (s *Server) useKubernetes() bool {
	return s.provider == "kubernetes"
}

func (s *Server) kubernetesUnavailableMessage() string {
	if strings.TrimSpace(s.kubernetesInitErr) != "" {
		return s.kubernetesInitErr
	}
	return "kubernetes client not initialized"
}

// Handler returns the root HTTP handler.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /runtime/status", s.handleRuntimeStatus)
	mux.HandleFunc("POST /deployments", s.handlePostDeployment)
	mux.HandleFunc("DELETE /deployments/{id}", s.handleDeleteDeploymentID)
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/exec", s.handleRuntimeServiceExec)
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/restart", s.handleRuntimeServiceRestart)
	mux.HandleFunc("GET /deployments/{id}/runtime/services/{service_id}/logs", s.handleRuntimeServiceLogs)
	mux.HandleFunc("POST /deployments/{id}/runtime/services/{service_id}/health-check", s.handleRuntimeServiceHealth)
	mux.HandleFunc("POST /deployments/{id}/runtime/traffic-tests", s.handleRuntimeTrafficTests)
	mux.HandleFunc("GET /deployments/{id}/runtime/logs", s.handleRuntimeDeploymentLogs)
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

	prov := s.provider
	if prov == "" {
		prov = "docker"
	}
	st := model.RuntimeStatus{
		RuntimeProvider:     prov,
		CurrentContext:      s.k8sCtx,
		KubeconfigSource:    s.kubeconfigSource,
		KubernetesInitError: s.kubernetesInitErr,
	}

	if s.cli != nil {
		_, err := s.cli.Info()
		st.DockerReachable = err == nil
		if err != nil && st.Message == "" {
			st.Message = err.Error()
		}
	}

	if s.k8s != nil {
		err := rk8s.ProbeCluster(ctx, s.k8s)
		st.KubernetesReachable = err == nil
		if err != nil && st.Message == "" {
			st.Message = err.Error()
		}
	} else if s.kubernetesInitErr != "" {
		st.KubernetesReachable = false
		if st.Message == "" {
			st.Message = s.kubernetesInitErr
		}
	}

	switch prov {
	case "kubernetes":
		if st.KubernetesReachable {
			st.Status = "ok"
		} else {
			st.Status = "degraded"
			if st.KubernetesInitError == "" && s.kubernetesInitErr != "" {
				st.KubernetesInitError = s.kubernetesInitErr
			}
		}
	default:
		if st.DockerReachable {
			st.Status = "ok"
		} else {
			st.Status = "degraded"
		}
	}

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

	var resp model.DeploymentResponse
	if s.useKubernetes() {
		if s.k8s == nil {
			msg := s.kubernetesUnavailableMessage()
			resp = model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Error: &msg}
		} else {
			resp = rk8s.Deploy(ctx, s.k8s, &req)
		}
	} else {
		if s.cli == nil {
			msg := "docker client not initialized"
			resp = model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Error: &msg}
		} else {
			resp = rdocker.DeploySimple(ctx, s.cli, &req)
		}
	}

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
	projectID := r.URL.Query().Get("project_id")
	ctx, cancel := s.ctx(r)
	defer cancel()

	var resp model.DeploymentResponse
	if s.useKubernetes() {
		if s.k8s == nil {
			msg := s.kubernetesUnavailableMessage()
			resp = model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Error: &msg}
		} else {
			events := rk8s.DestroyDeployment(ctx, s.k8s, topologyID, deploymentID, projectID)
			resp = model.DeploymentResponse{Status: "succeeded", RuntimeProvider: "kubernetes"}
			for _, e := range events {
				resp.Events = append(resp.Events, e)
			}
		}
	} else {
		if s.cli == nil {
			msg := "docker client not initialized"
			resp = model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Error: &msg}
		} else {
			events := rdocker.DestroyDeployment(ctx, s.cli, deploymentID, topologyID)
			resp = model.DeploymentResponse{Status: "succeeded", RuntimeProvider: "docker"}
			for _, e := range events {
				resp.Events = append(resp.Events, e)
			}
		}
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
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
	projectID := r.URL.Query().Get("project_id")
	ctx, cancel := s.ctx(r)
	defer cancel()

	if s.useKubernetes() {
		if s.k8s == nil {
			http.Error(w, s.kubernetesUnavailableMessage(), http.StatusInternalServerError)
			return
		}
		out := rk8s.GetDeploymentStatus(ctx, s.k8s, topologyID, deploymentID, projectID)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(out)
		return
	}

	if s.cli == nil {
		http.Error(w, "docker client not initialized", http.StatusInternalServerError)
		return
	}
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
	projectID := r.URL.Query().Get("project_id")
	tail, _ := strconv.Atoi(r.URL.Query().Get("tail"))
	if nodeID == "" || topologyID == "" {
		http.Error(w, "node_id and topology_id query parameters are required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()

	if s.useKubernetes() {
		if s.k8s == nil {
			msg := s.kubernetesUnavailableMessage()
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			_ = json.NewEncoder(w).Encode(model.LogsResponse{DeploymentID: deploymentID, NodeID: nodeID, Error: &msg})
			return
		}
		logs, err := rk8s.LogsForNode(ctx, s.k8s, topologyID, deploymentID, projectID, nodeID, int64(tail))
		if err != nil {
			msg := err.Error()
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			_ = json.NewEncoder(w).Encode(model.LogsResponse{DeploymentID: deploymentID, NodeID: nodeID, Error: &msg})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(model.LogsResponse{DeploymentID: deploymentID, NodeID: nodeID, Logs: logs})
		return
	}

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

	var resp model.TrafficResponse
	if s.useKubernetes() {
		if s.k8s == nil || s.k8sCfg == nil {
			msg := s.kubernetesUnavailableMessage()
			resp = model.TrafficResponse{ExitCode: 1, Success: false, Error: &msg}
		} else {
			resp = rk8s.RunTrafficTest(ctx, s.k8sCfg, s.k8s, &req)
		}
	} else {
		resp = rdocker.RunTrafficTest(ctx, s.cli, &req)
	}
	code := http.StatusOK
	if !resp.Success && resp.Error != nil {
		code = http.StatusBadRequest
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(resp)
}

func queryProjectID(r *http.Request) *string {
	q := strings.TrimSpace(r.URL.Query().Get("project_id"))
	if q == "" {
		return nil
	}
	return &q
}

func parseTailQuery(r *http.Request) int {
	t, _ := strconv.Atoi(r.URL.Query().Get("tail"))
	return t
}

func (s *Server) handleRuntimeDeploymentLogs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	topologyID := strings.TrimSpace(r.URL.Query().Get("topology_id"))
	projectID := strings.TrimSpace(r.URL.Query().Get("project_id"))
	tail := parseTailQuery(r)
	if topologyID == "" {
		http.Error(w, "topology_id query parameter is required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()

	if s.useKubernetes() {
		if s.k8s == nil {
			writeRuntimeLogsError(w, http.StatusInternalServerError, deploymentID, "", "kubernetes", s.kubernetesUnavailableMessage())
			return
		}
		tail64 := int64(tail)
		if tail64 <= 0 {
			tail64 = 100
		}
		if tail64 > 5000 {
			tail64 = 5000
		}
		out := rk8s.RuntimeDeploymentLogs(ctx, s.k8s, topologyID, deploymentID, projectID, tail64)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
		return
	}
	if s.cli == nil {
		writeRuntimeLogsError(w, http.StatusServiceUnavailable, deploymentID, "", "docker", "docker client not initialized")
		return
	}
	out := rdocker.RuntimeDeploymentLogs(ctx, s.cli, topologyID, deploymentID, tail)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}

func writeRuntimeLogsError(w http.ResponseWriter, status int, deploymentID, serviceID, provider, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if provider == "" {
		provider = "docker"
	}
	_ = json.NewEncoder(w).Encode(model.RuntimeDeploymentLogsResponse{
		DeploymentID:    deploymentID,
		ServiceID:       serviceID,
		Logs:            msg,
		Items:           []model.RuntimeLogsItem{},
		RuntimeProvider: provider,
	})
}

func (s *Server) handleRuntimeServiceLogs(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	nodeID := strings.TrimSpace(r.PathValue("service_id"))
	topologyID := strings.TrimSpace(r.URL.Query().Get("topology_id"))
	projectID := strings.TrimSpace(r.URL.Query().Get("project_id"))
	tail := parseTailQuery(r)
	if nodeID == "" || topologyID == "" {
		http.Error(w, "service_id path and topology_id query parameter are required", http.StatusBadRequest)
		return
	}
	ctx, cancel := s.ctx(r)
	defer cancel()

	out := model.RuntimeDeploymentLogsResponse{
		DeploymentID:    deploymentID,
		ServiceID:       nodeID,
		RuntimeProvider: "docker",
		Items:           []model.RuntimeLogsItem{},
	}
	if s.useKubernetes() {
		out.RuntimeProvider = "kubernetes"
		if s.k8s == nil {
			writeRuntimeLogsError(w, http.StatusInternalServerError, deploymentID, nodeID, "kubernetes", s.kubernetesUnavailableMessage())
			return
		}
		tail64 := int64(tail)
		if tail64 <= 0 {
			tail64 = 100
		}
		if tail64 > 5000 {
			tail64 = 5000
		}
		logs, err := rk8s.LogsForNode(ctx, s.k8s, topologyID, deploymentID, projectID, nodeID, tail64)
		if err != nil {
			out.Logs = err.Error()
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			_ = json.NewEncoder(w).Encode(out)
			return
		}
		out.Logs = logs
		out.Items = []model.RuntimeLogsItem{{ServiceID: nodeID, NodeID: nodeID, Logs: logs}}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
		return
	}
	if s.cli == nil {
		writeRuntimeLogsError(w, http.StatusServiceUnavailable, deploymentID, nodeID, "docker", "docker client not initialized")
		return
	}
	logs, err := rdocker.LogsForNode(ctx, s.cli, topologyID, nodeID, tail)
	if err != nil {
		out.Logs = err.Error()
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(out)
		return
	}
	out.Logs = logs
	out.Items = []model.RuntimeLogsItem{{ServiceID: nodeID, NodeID: nodeID, Logs: logs}}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(out)
}

func (s *Server) handleRuntimeServiceHealth(w http.ResponseWriter, r *http.Request) {
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
	var probe model.RuntimeHealthProbeRequest
	_ = json.NewDecoder(r.Body).Decode(&probe)

	ctx, cancel := s.ctx(r)
	defer cancel()
	start := time.Now()
	var resp model.RuntimeHealthResponse
	if s.useKubernetes() {
		if s.k8s == nil || s.k8sCfg == nil {
			resp = model.RuntimeHealthResponse{Status: "unsupported", Target: "", Message: s.kubernetesUnavailableMessage()}
			ms := time.Since(start).Milliseconds()
			resp.LatencyMs = &ms
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(resp)
			return
		}
		resp = rk8s.HealthCheckNode(ctx, s.k8sCfg, s.k8s, topologyID, deploymentID, projectID, nodeID, probe)
	} else {
		if s.cli == nil {
			resp = model.RuntimeHealthResponse{Status: "failed", Target: "", Message: "docker client not initialized"}
			ms := time.Since(start).Milliseconds()
			resp.LatencyMs = &ms
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusServiceUnavailable)
			_ = json.NewEncoder(w).Encode(resp)
			return
		}
		resp = rdocker.HealthCheckNode(ctx, s.cli, topologyID, nodeID, probe)
	}
	ms := time.Since(start).Milliseconds()
	resp.LatencyMs = &ms
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(resp)
}

func (s *Server) handleRuntimeTrafficTests(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	deploymentID := r.PathValue("id")
	var req model.RuntimeTrafficOpRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(req.TopologyID) == "" {
		req.TopologyID = strings.TrimSpace(r.URL.Query().Get("topology_id"))
	}
	if strings.TrimSpace(req.DeploymentID) == "" {
		req.DeploymentID = deploymentID
	}
	if req.ProjectID == nil {
		req.ProjectID = queryProjectID(r)
	}
	ctx, cancel := s.ctx(r)
	defer cancel()
	start := time.Now()
	var out model.RuntimeTrafficOpResponse
	if s.useKubernetes() {
		if s.k8s == nil || s.k8sCfg == nil {
			out = model.RuntimeTrafficOpResponse{
				Status: "failed", Source: req.SourceNodeID, Target: req.Target, Protocol: req.Protocol,
				Output: s.kubernetesUnavailableMessage(),
			}
		} else {
			out = rk8s.RunRuntimeTrafficOp(ctx, s.k8sCfg, s.k8s, req)
		}
	} else {
		if s.cli == nil {
			out = model.RuntimeTrafficOpResponse{
				Status: "failed", Source: req.SourceNodeID, Target: req.Target, Protocol: req.Protocol,
				Output: "docker client not initialized",
			}
		} else {
			out = rdocker.RunRuntimeTrafficOp(ctx, s.cli, req)
		}
	}
	ms := time.Since(start).Milliseconds()
	out.LatencyMs = &ms
	code := http.StatusOK
	if strings.Contains(out.Output, "client not initialized") {
		code = http.StatusServiceUnavailable
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(out)
}
