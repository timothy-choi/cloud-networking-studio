package api

import (
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/observability"
)

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func WithOperationTracing(provider string, inner http.Handler) http.Handler {
	return withOperationTracing(provider, inner)
}

func withOperationTracing(provider string, inner http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		op := operationFromRequest(r)
		rid := strings.TrimSpace(r.Header.Get("X-Request-ID"))
		deploymentID, topologyID := idsFromRequest(r)
		start := time.Now()

		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		inner.ServeHTTP(rec, r)

		if op == "" {
			if rid != "" {
				log.Printf(
					"cns-runner: %s %s request_id=%s status=%d duration_ms=%d provider=%s",
					r.Method, r.URL.Path, rid, rec.status, time.Since(start).Milliseconds(), provider,
				)
			}
			return
		}

		durationMs := time.Since(start).Milliseconds()
		statusLabel := "ok"
		errMsg := ""
		if rec.status >= 400 {
			statusLabel = "error"
			errMsg = http.StatusText(rec.status)
			if errMsg == "" {
				errMsg = "request failed"
			}
		}

		observability.RecordOperation(observability.OperationRecord{
			Operation:    op,
			Provider:     provider,
			Status:       statusLabel,
			DurationMs:   durationMs,
			RequestID:    rid,
			DeploymentID: deploymentID,
			TopologyID:   topologyID,
			ErrorMessage: errMsg,
			CreatedAt:    time.Now().UTC(),
		})

		log.Printf(
			"cns-runner: operation=%s request_id=%s deployment_id=%s topology_id=%s provider=%s duration_ms=%d status=%s http=%d",
			op,
			rid,
			deploymentID,
			topologyID,
			provider,
			durationMs,
			statusLabel,
			rec.status,
		)
	})
}

func operationFromRequest(r *http.Request) string {
	p := r.URL.Path
	switch {
	case r.Method == http.MethodPost && p == "/deployments":
		return "deploy"
	case r.Method == http.MethodDelete && strings.HasPrefix(p, "/deployments/"):
		return "destroy"
	case r.Method == http.MethodGet && strings.Contains(p, "/runtime/logs"):
		return "logs"
	case r.Method == http.MethodGet && strings.Contains(p, "/logs"):
		return "logs"
	case r.Method == http.MethodPost && strings.Contains(p, "/exec"):
		return "exec"
	case r.Method == http.MethodPost && strings.Contains(p, "/health-check"):
		return "health_check"
	case r.Method == http.MethodPost && (strings.Contains(p, "/traffic-tests") || p == "/traffic-tests"):
		return "traffic_test"
	case r.Method == http.MethodPost && strings.Contains(p, "/restart"):
		return "restart"
	default:
		return ""
	}
}

func idsFromRequest(r *http.Request) (deploymentID, topologyID string) {
	p := r.URL.Path
	if strings.HasPrefix(p, "/deployments/") {
		rest := strings.TrimPrefix(p, "/deployments/")
		if idx := strings.Index(rest, "/"); idx >= 0 {
			deploymentID = rest[:idx]
		} else {
			deploymentID = rest
		}
	}
	topologyID = strings.TrimSpace(r.URL.Query().Get("topology_id"))
	return deploymentID, topologyID
}

func parseLimitQuery(r *http.Request, defaultLimit, maxLimit int) int {
	raw := strings.TrimSpace(r.URL.Query().Get("limit"))
	if raw == "" {
		return defaultLimit
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n <= 0 {
		return defaultLimit
	}
	if n > maxLimit {
		return maxLimit
	}
	return n
}
