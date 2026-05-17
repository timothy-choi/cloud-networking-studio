package kubernetes

import (
	"context"
	"fmt"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

// DestroyNamespace deletes a namespace (cascade).
func DestroyNamespace(ctx context.Context, client kubernetes.Interface, ns string) error {
	err := client.CoreV1().Namespaces().Delete(ctx, ns, metav1.DeleteOptions{})
	if err != nil && !apierrors.IsNotFound(err) {
		return err
	}
	return nil
}

// DestroyDeployment resolves the namespace from topology/deployment/project and deletes it.
func DestroyDeployment(ctx context.Context, client kubernetes.Interface, topologyID, deploymentID, projectID string) []model.Event {
	ev := func(level, msg string) model.Event { return model.Event{Level: level, Message: msg} }
	var events []model.Event
	ns := NamespaceFor(projectID, topologyID, deploymentID)
	events = append(events, ev("info", fmt.Sprintf("Kubernetes: deleting namespace %s", ns)))
	if err := DestroyNamespace(ctx, client, ns); err != nil {
		events = append(events, ev("warning", fmt.Sprintf("namespace delete issue: %v", err)))
	} else {
		events = append(events, ev("info", "Kubernetes namespace delete requested"))
	}
	events = append(events, ev("info", "Runtime resources destroyed"))
	return events
}
