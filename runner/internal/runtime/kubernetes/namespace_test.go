package kubernetes

import "testing"

func TestNamespaceFor_WithProject(t *testing.T) {
	pid := "11111111-1111-1111-1111-111111111111"
	top := "22222222-2222-2222-2222-222222222222"
	dep := "33333333-3333-3333-3333-333333333333"
	got := NamespaceFor(pid, top, dep)
	if got == "" {
		t.Fatal("empty namespace")
	}
	if len(got) > 63 {
		t.Fatalf("namespace too long: %d %q", len(got), got)
	}
	if got[:4] != "cns-" {
		t.Fatalf("unexpected prefix %q", got)
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
