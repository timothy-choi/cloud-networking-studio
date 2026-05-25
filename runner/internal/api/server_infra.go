package api

import (
	"encoding/json"
	"net/http"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/infra"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func (s *Server) handlePostInfraExecution(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := s.ctx(r)
	defer cancel()

	var req model.InfraExecutionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "invalid JSON body"})
		return
	}

	resp := infra.Execute(ctx, req)
	if resp.Status != "succeeded" {
		w.WriteHeader(http.StatusUnprocessableEntity)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	_ = json.NewEncoder(w).Encode(resp)
}
