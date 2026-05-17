package kubernetes

import (
	"context"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

// LogsForNode returns aggregated container logs for the pod matching node_id labels.
func LogsForNode(ctx context.Context, client kubernetes.Interface, topologyID, deploymentID, projectID, nodeID string, tail int64) (string, error) {
	ns := NamespaceFor(projectID, topologyID, deploymentID)
	if tail <= 0 {
		tail = 100
	}
	if tail > 5000 {
		tail = 5000
	}
	tailLines := tail
	sel := "cns.io/node-id=" + strings.TrimSpace(nodeID)
	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{LabelSelector: sel})
	if err != nil {
		return "", err
	}
	if len(pods.Items) == 0 {
		return "", fmt.Errorf("no pod for topology %s node %s in namespace %s", topologyID, nodeID, ns)
	}
	p := pods.Items[0]
	req := client.CoreV1().Pods(ns).GetLogs(p.Name, &corev1.PodLogOptions{
		Container: cnsContainerName,
		TailLines: &tailLines,
	})
	stream, err := req.Stream(ctx)
	if err != nil {
		return "", err
	}
	defer stream.Close()
	var buf strings.Builder
	tmp := make([]byte, 4096)
	for {
		n, err := stream.Read(tmp)
		if n > 0 {
			buf.Write(tmp[:n])
		}
		if err != nil {
			break
		}
	}
	return buf.String(), nil
}
