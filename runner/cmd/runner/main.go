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

func withDeploymentRequestLogging(inner http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		p := r.URL.Path
		switch {
		case r.Method == http.MethodPost && p == "/deployments":
			log.Printf("cns-runner: POST /deployments")
		case r.Method == http.MethodDelete && strings.HasPrefix(p, "/deployments/"):
			log.Printf("cns-runner: DELETE %s", p)
		case r.Method == http.MethodGet && strings.HasPrefix(p, "/deployments/") && !strings.Contains(p, "/logs"):
			log.Printf("cns-runner: GET %s", p)
		}
		inner.ServeHTTP(w, r)
	})
}
