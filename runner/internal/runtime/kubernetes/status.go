package kubernetes

import (
	"context"

	corev1 "k8s.io/api/core/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

// GetDeploymentStatus lists workloads in the deployment namespace and aggregates phase.
func GetDeploymentStatus(ctx context.Context, client kubernetes.Interface, topologyID, deploymentID, projectID string) model.DeploymentGetResponse {
	ns := NamespaceFor(projectID, topologyID, deploymentID)
	out := model.DeploymentGetResponse{
		DeploymentID:    deploymentID,
		TopologyID:      topologyID,
		RuntimeProvider: "kubernetes",
		Namespace:       ns,
		Status:          "pending",
	}

	_, err := client.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		out.Status = "destroyed"
		out.Resources = []model.ResourceRef{}
		return out
	}
	if err != nil {
		msg := err.Error()
		out.Status = "failed"
		out.Error = &msg
		return out
	}

	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{})
	if err != nil {
		msg := err.Error()
		out.Status = "failed"
		out.Error = &msg
		return out
	}
	deps, _ := client.AppsV1().Deployments(ns).List(ctx, metav1.ListOptions{})
	svcs, _ := client.CoreV1().Services(ns).List(ctx, metav1.ListOptions{})
	cms, _ := client.CoreV1().ConfigMaps(ns).List(ctx, metav1.ListOptions{})

	var refs []model.ResourceRef
	for _, p := range pods.Items {
		refs = append(refs, model.ResourceRef{Kind: "Pod", Name: p.Name, Namespace: ns})
	}
	if deps != nil {
		for _, d := range deps.Items {
			refs = append(refs, model.ResourceRef{Kind: "Deployment", Name: d.Name, Namespace: ns})
		}
	}
	if svcs != nil {
		for _, s := range svcs.Items {
			if s.Name == "kubernetes" {
				continue
			}
			refs = append(refs, model.ResourceRef{Kind: "Service", Name: s.Name, Namespace: ns})
		}
	}
	if cms != nil {
		for _, c := range cms.Items {
			refs = append(refs, model.ResourceRef{Kind: "ConfigMap", Name: c.Name, Namespace: ns})
		}
	}
	out.Resources = refs

	if len(pods.Items) == 0 {
		out.Status = "pending"
		return out
	}
	allRunning := true
	anyFailed := false
	anyPending := false
	for _, p := range pods.Items {
		switch p.Status.Phase {
		case corev1.PodFailed:
			anyFailed = true
		case corev1.PodPending, corev1.PodUnknown:
			anyPending = true
			allRunning = false
		case corev1.PodSucceeded:
			allRunning = false
		case corev1.PodRunning:
			for _, c := range p.Status.ContainerStatuses {
				if !c.Ready {
					allRunning = false
					anyPending = true
				}
			}
		default:
			allRunning = false
		}
	}
	switch {
	case anyFailed:
		out.Status = "failed"
	case anyPending || !allRunning:
		out.Status = "pending"
	default:
		out.Status = "running"
	}
	var ids []string
	for _, p := range pods.Items {
		ids = append(ids, string(p.UID))
	}
	out.ContainerIDs = ids
	return out
}

// ProbeCluster returns nil if API server responds.
func ProbeCluster(ctx context.Context, client kubernetes.Interface) error {
	_, err := client.CoreV1().Namespaces().List(ctx, metav1.ListOptions{Limit: 1})
	return err
}
