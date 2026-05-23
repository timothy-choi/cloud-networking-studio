package main

import (
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/api"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime"
)

func main() {
	addr := ":8090"
	if v := os.Getenv("RUNNER_LISTEN_ADDR"); v != "" {
		addr = v
	}
	srv, err := api.NewServer()
	if err != nil {
		log.Fatalf("runner init: %v", err)
	}
	log.Printf("cns-runner listening on %s (RUNTIME_PROVIDER=%s)", addr, runtime.RuntimeProviderEnv())
	log.Fatal(http.ListenAndServe(addr, withDeploymentRequestLogging(srv.Handler())))
}

func withRequestIdLogging(inner http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rid := strings.TrimSpace(r.Header.Get("X-Request-ID"))
		p := r.URL.Path
		switch {
		case r.Method == http.MethodPost && p == "/deployments":
			if rid != "" {
				log.Printf("cns-runner: POST /deployments request_id=%s", rid)
			} else {
				log.Printf("cns-runner: POST /deployments")
			}
		case r.Method == http.MethodDelete && strings.HasPrefix(p, "/deployments/"):
			if rid != "" {
				log.Printf("cns-runner: DELETE %s request_id=%s", p, rid)
			} else {
				log.Printf("cns-runner: DELETE %s", p)
			}
		case r.Method == http.MethodGet && strings.HasPrefix(p, "/deployments/") && !strings.Contains(p, "/logs"):
			if rid != "" {
				log.Printf("cns-runner: GET %s request_id=%s", p, rid)
			} else {
				log.Printf("cns-runner: GET %s", p)
			}
		default:
			if rid != "" {
				log.Printf("cns-runner: %s %s request_id=%s", r.Method, p, rid)
			}
		}
		inner.ServeHTTP(w, r)
	})
}

func withDeploymentRequestLogging(inner http.Handler) http.Handler {
	return withRequestIdLogging(inner)
}
