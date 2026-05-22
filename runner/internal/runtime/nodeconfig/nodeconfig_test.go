package nodeconfig

import (
	"testing"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func TestResolveContainerCommandCustomOverridesDefault(t *testing.T) {
	img := "nginx:alpine"
	cmd := []string{"custom", "entry"}
	pn := model.PlanNode{Command: cmd, NodeType: "generic", Image: &img}
	got := ResolveContainerCommand(pn, "nginx:alpine")
	if len(got) != 2 || got[0] != "custom" {
		t.Fatalf("got %v", got)
	}
}

func TestEffectivePortsCustom(t *testing.T) {
	pn := model.PlanNode{
		Ports: []model.RuntimePort{{Port: 8080, TargetPort: 8080, Protocol: "TCP"}},
	}
	ports := EffectivePorts(pn)
	if len(ports) != 1 || ports[0].Port != 8080 {
		t.Fatalf("got %+v", ports)
	}
}

func TestPlanNodeRuntimeMetaIncludesEnv(t *testing.T) {
	pn := model.PlanNode{
		Env: map[string]string{"LAB": "1"},
	}
	meta := PlanNodeRuntimeMeta(pn, "busybox:latest", []string{"sleep", "infinity"})
	if meta["env"] == "" {
		t.Fatalf("expected env in metadata: %+v", meta)
	}
}
