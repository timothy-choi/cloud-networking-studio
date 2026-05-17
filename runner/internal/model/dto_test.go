package model

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDeploymentResponseJSON_RuntimeAccessShape(t *testing.T) {
	resp := DeploymentResponse{
		Status:          "succeeded",
		RuntimeProvider: "kubernetes",
		Events:          []Event{{Level: "info", Message: "ok"}},
		RuntimeAccess: &RuntimeAccess{
			DeploymentID:       "d1",
			TopologyID:         "t1",
			Status:             "running",
			RuntimeProvider:    "kubernetes",
			NamespaceOrNetwork: "ns-a",
			Resources: []RuntimeAccessResource{
				{
					Type:               "service",
					Name:               "api",
					RuntimeName:        "cns-svc",
					NamespaceOrNetwork: "ns-a",
					Ports:              []RuntimePort{{Port: 80, TargetPort: 8080, Protocol: "TCP"}},
					InternalURL:        "http://cns-svc.ns-a.svc.cluster.local:80",
				},
			},
		},
	}
	b, err := json.Marshal(resp)
	if err != nil {
		t.Fatal(err)
	}
	raw := string(b)
	if !strings.Contains(raw, `"runtime_access"`) {
		t.Fatalf("missing runtime_access key: %s", raw)
	}
	if !strings.Contains(raw, `"namespace_or_network":"ns-a"`) {
		t.Fatalf("unexpected json: %s", raw)
	}
}

func TestDeploymentResponseJSON_OmitsNilRuntimeAccess(t *testing.T) {
	resp := DeploymentResponse{
		Status:          "succeeded",
		RuntimeProvider: "docker",
		Events:          []Event{{Level: "info", Message: "ok"}},
	}
	b, err := json.Marshal(resp)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(b), "runtime_access") {
		t.Fatalf("expected omit: %s", string(b))
	}
}
