package runtime

import (
	"testing"
)

func TestRuntimeProviderEnv_DefaultDocker(t *testing.T) {
	t.Setenv("RUNTIME_PROVIDER", "")
	if g, w := RuntimeProviderEnv(), "docker"; g != w {
		t.Fatalf("got %q want %q", g, w)
	}
}

func TestRuntimeProviderEnv_Explicit(t *testing.T) {
	for _, tc := range []struct {
		in, want string
	}{
		{"docker", "docker"},
		{"DOCKER", "docker"},
		{"kubernetes", "kubernetes"},
		{"KUBERNETES", "kubernetes"},
		{"k8s", "kubernetes"},
		{"bogus", "docker"},
	} {
		t.Run(tc.in, func(t *testing.T) {
			t.Setenv("RUNTIME_PROVIDER", tc.in)
			if g := RuntimeProviderEnv(); g != tc.want {
				t.Fatalf("RUNTIME_PROVIDER=%q: got %q want %q", tc.in, g, tc.want)
			}
		})
	}
}
