package kubernetes

import "testing"

func TestNamespaceFor_WithProject(t *testing.T) {
	dep := "33333333-3333-3333-3333-333333333333"
	got := NamespaceFor("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222", dep)
	if got != "cns-deploy-33333333" {
		t.Fatalf("got %q", got)
	}
	if len(got) > 63 {
		t.Fatalf("namespace too long: %d %q", len(got), got)
	}
}

func TestNamespaceFor_NoProject(t *testing.T) {
	top := "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
	dep := "ffffffff-ffff-ffff-ffff-ffffffffffff"
	got := NamespaceFor("", top, dep)
	if got == "" {
		t.Fatal("empty namespace")
	}
}
