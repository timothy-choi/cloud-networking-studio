package kubernetes

import "testing"

func TestNamespaceForDeployPattern(t *testing.T) {
	dep := "33333333-3333-3333-3333-333333333333"
	got := NamespaceFor("", "", dep)
	if got != "cns-deploy-33333333" {
		t.Fatalf("got %q", got)
	}
}

func TestProductionBlockedLocalContext(t *testing.T) {
	meta := ClientMeta{Context: "kind-cns-runtime", LocalDevCluster: true}
	msg := ProductionBlocked(meta, "production")
	if msg == "" {
		t.Fatal("expected production block for kind context")
	}
}

func TestProductionAllowedNonLocal(t *testing.T) {
	meta := ClientMeta{Context: "eks-prod", ServerURL: "https://eks.example.com", LocalDevCluster: false}
	msg := ProductionBlocked(meta, "production")
	if msg != "" {
		t.Fatalf("unexpected block: %q", msg)
	}
}
