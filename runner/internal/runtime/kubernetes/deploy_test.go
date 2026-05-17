package kubernetes

import (
	"context"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func TestDeploy_MinimalCreatesNamespace(t *testing.T) {
	ctx := context.Background()
	client := fake.NewSimpleClientset()
	pid := "11111111-1111-1111-1111-111111111111"
	top := "22222222-2222-2222-2222-222222222222"
	dep := "33333333-3333-3333-3333-333333333333"
	req := &model.DeploymentRequest{
		DeploymentID:      dep,
		ProjectID:         &pid,
		TopologyID:        top,
		RuntimeTarget:     "docker",
		NetworkingMode:    "bridge",
		SegmentedNetworks: false,
		Nodes: []model.PlanNode{
			{ID: "node-1", Name: "n1", NodeType: "leaf"},
		},
	}
	resp := Deploy(ctx, client, req)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", *resp.Error)
	}
	if resp.Status != "succeeded" {
		t.Fatalf("status %q events=%+v", resp.Status, resp.Events)
	}
	ns := NamespaceFor(pid, top, dep)
	_, err := client.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
}

func TestDeploy_SegmentedRejected(t *testing.T) {
	ctx := context.Background()
	client := fake.NewSimpleClientset()
	req := &model.DeploymentRequest{
		DeploymentID:      "d",
		TopologyID:        "550e8400-e29b-41d4-a716-446655440000",
		SegmentedNetworks: true,
		Nodes:             []model.PlanNode{{ID: "x", Name: "x", NodeType: "leaf"}},
	}
	resp := Deploy(ctx, client, req)
	if resp.Error == nil || resp.Status != "failed" {
		t.Fatalf("want failed, got %+v", resp)
	}
}
