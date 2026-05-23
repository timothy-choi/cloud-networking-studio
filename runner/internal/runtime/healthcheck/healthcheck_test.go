package healthcheck

import (
	"testing"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func TestResolveProbeSpecNginxDefaultsHTTP(t *testing.T) {
	img := "nginx:alpine"
	pn := model.PlanNode{Image: &img, Ports: []model.RuntimePort{{Port: 80, TargetPort: 80}}}
	spec := ResolveProbeSpec(pn, map[string]interface{}{"path": "/"})
	if spec.CheckType != "http" {
		t.Fatalf("got %q", spec.CheckType)
	}
	if spec.Port != 80 {
		t.Fatalf("port %d", spec.Port)
	}
}

func TestResolveProbeSpecUbuntuDefaultsRuntime(t *testing.T) {
	img := "ubuntu:22.04"
	pn := model.PlanNode{Image: &img, Command: []string{"sleep", "infinity"}}
	spec := ResolveProbeSpec(pn, nil)
	if spec.CheckType != "runtime" {
		t.Fatalf("got %q", spec.CheckType)
	}
}

func TestResolveProbeSpecRedisTCP(t *testing.T) {
	img := "redis:7"
	pn := model.PlanNode{Image: &img}
	spec := ResolveProbeSpec(pn, map[string]interface{}{"check_type": "tcp", "port": 6379})
	if spec.CheckType != "tcp" || spec.Port != 6379 {
		t.Fatalf("got %+v", spec)
	}
}

func TestRunNoneCheck(t *testing.T) {
	resp := Run(ProbeSpec{CheckType: "none"}, nil, nil)
	if resp.Status != "unsupported" || resp.Message == "" {
		t.Fatalf("%+v", resp)
	}
}

func TestRunRuntimeCheck(t *testing.T) {
	resp := Run(ProbeSpec{CheckType: "runtime", Image: "ubuntu:22.04"}, nil, func() (bool, string, error) {
		return true, "running", nil
	})
	if resp.Status != "passed" {
		t.Fatalf("%+v", resp)
	}
}
