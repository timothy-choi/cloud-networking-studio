package docker

import (
	"context"
	"testing"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func TestRunRuntimeTrafficOpPingURLUnsupported(t *testing.T) {
	req := model.RuntimeTrafficOpRequest{
		TopologyID:   "t1",
		SourceNodeID: "src-node",
		Target:       "http://example.com/foo",
		Protocol:     "ping",
	}
	out := RunRuntimeTrafficOp(context.Background(), nil, req)
	if out.Status != "unsupported" || out.Protocol != "ping" {
		t.Fatalf("unexpected %+v", out)
	}
}
