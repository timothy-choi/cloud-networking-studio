package healthcheck

import (
	"strings"
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

func TestRunHTTPMissingToolUnsupported(t *testing.T) {
	resp := Run(ProbeSpec{CheckType: "http", Port: 80, Path: "/"}, func(argv []string) (string, string, int, error) {
		return "", "wget: not found\ncurl: not found", 127, nil
	}, nil)
	if resp.Status != "unsupported" {
		t.Fatalf("got %+v", resp)
	}
	if resp.Message == "" || !contains(resp.Message, "Tool missing") {
		t.Fatalf("message %+v", resp.Message)
	}
}

func TestRunHTTPConnectionRefused(t *testing.T) {
	resp := Run(ProbeSpec{CheckType: "http", Port: 80, Path: "/"}, func(argv []string) (string, string, int, error) {
		if len(argv) > 0 && argv[0] == "wget" {
			return "", "Connecting to 127.0.0.1:80... failed: Connection refused.", 4, nil
		}
		return "000", "curl: (7) Failed to connect to 127.0.0.1 port 80: Connection refused", 7, nil
	}, nil)
	if resp.Status != "failed" {
		t.Fatalf("got %+v", resp)
	}
	if !contains(resp.Message, "No HTTP service appears to be running") {
		t.Fatalf("message %+v", resp.Message)
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || strings.Contains(s, sub))
}
