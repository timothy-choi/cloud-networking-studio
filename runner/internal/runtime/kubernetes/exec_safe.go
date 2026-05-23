package kubernetes

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

// SafeExecWorkload runs argv in the node pod with a deadline.
func SafeExecWorkload(
	ctx context.Context,
	cfg *rest.Config,
	client kubernetes.Interface,
	topologyID, deploymentID, projectID, nodeID string,
	argv []string,
	timeout time.Duration,
) (stdout, stderr string, exitCode int, status, message string) {
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	if timeout > 2*time.Minute {
		timeout = 2 * time.Minute
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	ns := NamespaceFor(strings.TrimSpace(projectID), topologyID, deploymentID)
	pod, err := podNameForNode(ctx, client, ns, nodeID)
	if err != nil || pod == "" {
		return "", "", -1, "failed", ""
	}
	out, errOut, code, err := podExec(ctx, cfg, client, ns, pod, argv)
	if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
		return out, errOut, code, "timeout", ""
	}
	if err != nil && code < 0 {
		return out, errOut, code, "failed", ""
	}
	combined := strings.TrimSpace(errOut + "\n" + out)
	if code != 0 {
		if trafficutil.ExecArgvToolMissing(argv, combined) {
			return strings.TrimSpace(out), strings.TrimSpace(errOut), code, "unsupported", trafficutil.ToolUnavailableMessage
		}
		return strings.TrimSpace(out), strings.TrimSpace(errOut), code, "failed", ""
	}
	_ = err
	return strings.TrimSpace(out), strings.TrimSpace(errOut), code, "succeeded", ""
}

// RestartWorkload deletes the pod so the Deployment controller recreates it.
func RestartWorkload(ctx context.Context, client kubernetes.Interface, topologyID, deploymentID, projectID, nodeID string) error {
	ns := NamespaceFor(strings.TrimSpace(projectID), topologyID, deploymentID)
	pod, err := podNameForNode(ctx, client, ns, nodeID)
	if err != nil {
		return err
	}
	if pod == "" {
		return fmt.Errorf("pod not found")
	}
	return client.CoreV1().Pods(ns).Delete(ctx, pod, metav1.DeleteOptions{})
}
