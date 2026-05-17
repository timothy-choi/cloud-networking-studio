package kubernetes

import (
	"context"
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestDestroyDeployment_DeletesNamespace(t *testing.T) {
	ctx := context.Background()
	top := "550e8400-e29b-41d4-a716-446655440000"
	dep := "660e8400-e29b-41d4-a716-446655440001"
	ns := NamespaceFor("", top, dep)
	client := fake.NewSimpleClientset()
	_, err := client.CoreV1().Namespaces().Create(ctx, &corev1.Namespace{
		ObjectMeta: metav1.ObjectMeta{Name: ns},
	}, metav1.CreateOptions{})
	if err != nil {
		t.Fatal(err)
	}
	events := DestroyDeployment(ctx, client, top, dep, "")
	if len(events) == 0 {
		t.Fatal("expected events")
	}
	_, err = client.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if err == nil {
		t.Fatal("expected namespace gone or terminating")
	}
}
