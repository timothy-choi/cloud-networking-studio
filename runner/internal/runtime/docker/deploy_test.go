package docker

import "testing"

func TestTopologyNetworkName(t *testing.T) {
	id := "550e8400-e29b-41d4-a716-446655440000"
	got := TopologyNetworkName(id)
	want := "cns-topology-550e8400e29b"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestContainerName(t *testing.T) {
	got := ContainerName("550e8400-e29b-41d4-a716-446655440000", "web-1")
	if got != "cns-node-550e8400e29b-web-1" {
		t.Fatalf("got %q", got)
	}
}

func TestResolveImageBlankRejected(t *testing.T) {
	blank := ""
	_, err := resolveImage(&blank, "host")
	if err == nil {
		t.Fatal("expected error for blank image")
	}
}
