package kubernetes

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/kubernetes/scheme"
	"k8s.io/client-go/rest"
	remotecommand "k8s.io/client-go/tools/remotecommand"
	executil "k8s.io/client-go/util/exec"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

// RunTrafficTest runs ping or wget inside the source pod toward the target pod IP.
func RunTrafficTest(ctx context.Context, cfg *rest.Config, client kubernetes.Interface, req *model.TrafficRequest) model.TrafficResponse {
	tid := strings.TrimSpace(req.TopologyID)
	src := strings.TrimSpace(req.SourceNodeID)
	tgt := strings.TrimSpace(req.TargetNodeID)
	if tid == "" || src == "" || tgt == "" {
		msg := "topology_id, source_node_id, and target_node_id are required"
		return model.TrafficResponse{ExitCode: 1, Success: false, Error: &msg}
	}
	ns := NamespaceFor(derefStr(req.ProjectID), tid, strings.TrimSpace(req.DeploymentID))
	srcPod, err := podNameForNode(ctx, client, ns, src)
	if err != nil || srcPod == "" {
		msg := "source pod not found"
		if err != nil {
			msg = err.Error()
		}
		return model.TrafficResponse{ExitCode: 127, Success: false, Stderr: msg, Error: &msg}
	}
	tgtIP, err := podIPForNode(ctx, client, ns, tgt)
	if err != nil || tgtIP == "" {
		msg := "could not resolve target pod IP"
		if err != nil {
			msg = err.Error()
		}
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}

	tt := strings.ToLower(strings.TrimSpace(req.Type))
	if tt == "" {
		tt = "ping"
	}
	count := req.Count
	if count <= 0 {
		count = 3
	}
	if count > 10 {
		count = 10
	}

	var argv []string
	switch tt {
	case "ping":
		argv = []string{"ping", "-c", fmt.Sprintf("%d", count), "-W", "2", tgtIP}
	case "http":
		port := req.Port
		if port <= 0 {
			port = 80
		}
		path := req.Path
		if path == "" {
			path = "/"
		}
		argv = []string{"wget", "-q", "-O-", "-T", "10", fmt.Sprintf("http://%s:%d%s", tgtIP, port, path)}
	default:
		msg := "type must be ping or http"
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}

	execReq := client.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(srcPod).
		Namespace(ns).
		VersionedParams(&corev1.PodExecOptions{
			Container: cnsContainerName,
			Command:   argv,
			Stdout:    true,
			Stderr:    true,
		}, scheme.ParameterCodec).
		SubResource("exec")

	executor, err := remotecommand.NewSPDYExecutor(cfg, "POST", execReq.URL())
	if err != nil {
		msg := err.Error()
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}
	var stdout, stderr bytes.Buffer
	err = executor.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: &stdout,
		Stderr: &stderr,
		Tty:    false,
	})
	exit := 0
	if err != nil {
		var ce executil.CodeExitError
		if errors.As(err, &ce) {
			exit = ce.ExitStatus()
		} else {
			exit = 1
		}
	}
	ok := exit == 0
	stdErr := stderr.String()
	var errPtr *string
	if strings.EqualFold(tt, "http") && !ok && trafficutil.HTTPWgetMissing(stdErr) {
		msg := "HTTP test tool is missing in client image"
		errPtr = &msg
	}
	return model.TrafficResponse{
		ExitCode: exit,
		Stdout:   stdout.String(),
		Stderr:   stdErr,
		Success:  ok,
		Error:    errPtr,
	}
}

func podNameForNode(ctx context.Context, client kubernetes.Interface, ns, nodeID string) (string, error) {
	sel := "cns.io/node-id=" + strings.TrimSpace(nodeID)
	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{LabelSelector: sel})
	if err != nil {
		return "", err
	}
	for _, p := range pods.Items {
		if p.Status.Phase == corev1.PodRunning || p.Status.Phase == corev1.PodPending {
			return p.Name, nil
		}
	}
	if len(pods.Items) > 0 {
		return pods.Items[0].Name, nil
	}
	return "", fmt.Errorf("no pod for node %s", nodeID)
}

func podIPForNode(ctx context.Context, client kubernetes.Interface, ns, nodeID string) (string, error) {
	sel := "cns.io/node-id=" + strings.TrimSpace(nodeID)
	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{LabelSelector: sel})
	if err != nil {
		return "", err
	}
	for _, p := range pods.Items {
		if p.Status.PodIP != "" {
			return p.Status.PodIP, nil
		}
	}
	return "", fmt.Errorf("no pod IP for node %s", nodeID)
}
