package kubernetes

import (
	"context"
	"strings"
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
	if resp.RuntimeAccess == nil {
		t.Fatal("RuntimeAccess should be set on success")
	}
	if resp.RuntimeAccess.RuntimeProvider != "kubernetes" {
		t.Fatalf("access runtime_provider %q", resp.RuntimeAccess.RuntimeProvider)
	}
	if resp.RuntimeAccess.NamespaceOrNetwork != ns {
		t.Fatalf("namespace_or_network %q want %q", resp.RuntimeAccess.NamespaceOrNetwork, ns)
	}
	foundClusterDNS := false
	for _, r := range resp.RuntimeAccess.Resources {
		if r.Type == "service" && strings.Contains(r.InternalURL, ".svc.cluster.local:") {
			foundClusterDNS = true
		}
	}
	if !foundClusterDNS {
		t.Fatalf("expected service internal cluster DNS URL in resources: %+v", resp.RuntimeAccess.Resources)
	}
	foundPF := false
	for _, r := range resp.RuntimeAccess.Resources {
		if r.Type == "service" && r.Metadata["public_access"] == "manual_port_forward_required" {
			foundPF = true
		}
	}
	if !foundPF {
		t.Fatalf("expected manual public access hint on service resource: %+v", resp.RuntimeAccess.Resources)
	}
	_, err := client.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if err != nil {
		t.Fatal(err)
	}
}

func TestDeploy_CustomNodeConfig(t *testing.T) {
	ctx := context.Background()
	client := fake.NewSimpleClientset()
	pid := "11111111-1111-1111-1111-111111111111"
	top := "22222222-2222-2222-2222-222222222222"
	dep := "33333333-3333-3333-3333-333333333333"
	img := "busybox:latest"
	role := "api"
	term := false
	desc := "custom"
	req := &model.DeploymentRequest{
		DeploymentID:      dep,
		ProjectID:         &pid,
		TopologyID:        top,
		RuntimeTarget:     "kubernetes",
		NetworkingMode:    "bridge",
		SegmentedNetworks: false,
		Nodes: []model.PlanNode{
			{
				ID:              "node-1",
				Name:            "api",
				NodeType:        "generic",
				Image:           &img,
				RoleLabel:       &role,
				Command:         []string{"sleep", "infinity"},
				Ports:           []model.RuntimePort{{Port: 8080, TargetPort: 8080, Protocol: "TCP"}},
				Env:             map[string]string{"LAB": "1"},
				TerminalEnabled: &term,
				Description:     &desc,
				HealthCheck:     map[string]interface{}{"path": "/healthz", "port": 8080},
			},
		},
	}
	resp := Deploy(ctx, client, req)
	if resp.Error != nil {
		t.Fatalf("unexpected error: %v", *resp.Error)
	}
	if resp.Status != "succeeded" {
		t.Fatalf("status %q", resp.Status)
	}
	var svcRes *model.RuntimeAccessResource
	for i := range resp.RuntimeAccess.Resources {
		if resp.RuntimeAccess.Resources[i].Type == "service" {
			svcRes = &resp.RuntimeAccess.Resources[i]
			break
		}
	}
	if svcRes == nil {
		t.Fatal("missing service resource")
	}
	if len(svcRes.Ports) != 1 || svcRes.Ports[0].Port != 8080 {
		t.Fatalf("ports %+v", svcRes.Ports)
	}
	if svcRes.Metadata["role_label"] != "api" {
		t.Fatalf("metadata %+v", svcRes.Metadata)
	}
	if svcRes.Metadata["env"] == "" {
		t.Fatalf("expected env metadata")
	}
	if !strings.Contains(svcRes.InternalURL, ":8080") {
		t.Fatalf("internal url %q", svcRes.InternalURL)
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
