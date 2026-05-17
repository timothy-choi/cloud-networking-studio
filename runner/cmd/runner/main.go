package main

import (
	"log"
	"net/http"
	"os"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/api"
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
	log.Printf("cns-runner listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, srv.Handler()))
}
