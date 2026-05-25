package main

import (
	"log"
	"net/http"
	"os"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/api"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo"
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
	log.Printf("cns-runner listening on %s (RUNTIME_PROVIDER=%s version=%s)", addr, runtime.RuntimeProviderEnv(), buildinfo.Version)
	log.Fatal(http.ListenAndServe(addr, api.WithOperationTracing(runtime.RuntimeProviderEnv(), srv.Handler())))
}
