package kubernetes

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestGetDeploymentStatus_DestroyedWhenNamespaceMissing(t *testing.T) {
	ctx := context.Background()
	client := fake.NewSimpleClientset()
	out := GetDeploymentStatus(ctx, client, "550e8400-e29b-41d4-a716-446655440000", "660e8400-e29b-41d4-a716-446655440001", "")
	if out.Status != "destroyed" {
		t.Fatalf("got %+v", out)
	}
	if out.RuntimeProvider != "kubernetes" {
		t.Fatalf("provider %q", out.RuntimeProvider)
	}
}

func TestGetDeploymentStatus_EmptyNamespacePending(t *testing.T) {
	ctx := context.Background()
	top := "550e8400-e29b-41d4-a716-446655440000"
	dep := "660e8400-e29b-41d4-a716-446655440001"
	ns := NamespaceFor("", top, dep)
	client := fake.NewSimpleClientset(&corev1.Namespace{
		ObjectMeta: metav1.ObjectMeta{Name: ns},
	})
	out := GetDeploymentStatus(ctx, client, top, dep, "")
	if out.Status != "pending" {
		t.Fatalf("got %+v", out)
	}
}
