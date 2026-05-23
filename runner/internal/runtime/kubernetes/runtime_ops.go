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
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/healthcheck"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

func podExec(ctx context.Context, cfg *rest.Config, client kubernetes.Interface, ns, podName string, argv []string) (stdout, stderr string, exitCode int, err error) {
	execReq := client.CoreV1().RESTClient().Post().
		Resource("pods").
		Name(podName).
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
		return "", "", -1, err
	}
	var outBuf, errBuf bytes.Buffer
	err = executor.StreamWithContext(ctx, remotecommand.StreamOptions{
		Stdout: &outBuf,
		Stderr: &errBuf,
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
	return outBuf.String(), errBuf.String(), exit, err
}

// RuntimeDeploymentLogs aggregates pod logs for each node workload in the deployment namespace.
func RuntimeDeploymentLogs(ctx context.Context, client kubernetes.Interface, topologyID, deploymentID, projectID string, tail int64) model.RuntimeDeploymentLogsResponse {
	ns := NamespaceFor(strings.TrimSpace(projectID), topologyID, deploymentID)
	out := model.RuntimeDeploymentLogsResponse{
		DeploymentID:    strings.TrimSpace(deploymentID),
		RuntimeProvider: "kubernetes",
		Items:           []model.RuntimeLogsItem{},
	}
	if strings.TrimSpace(topologyID) == "" || strings.TrimSpace(deploymentID) == "" {
		out.Logs = "topology_id and deployment_id are required"
		return out
	}
	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{})
	if err != nil {
		out.Logs = err.Error()
		return out
	}
	seen := map[string]struct{}{}
	for _, p := range pods.Items {
		if p.Labels == nil {
			continue
		}
		nid := strings.TrimSpace(p.Labels["cns.io/node-id"])
		if nid == "" {
			continue
		}
		if _, ok := seen[nid]; ok {
			continue
		}
		seen[nid] = struct{}{}
		name := strings.TrimSpace(p.Name)
		item := model.RuntimeLogsItem{NodeID: nid, ServiceID: nid, Name: name}
		logs, logErr := LogsForNode(ctx, client, topologyID, deploymentID, projectID, nid, tail)
		if logErr != nil {
			item.Error = logErr.Error()
		} else {
			item.Logs = logs
		}
		out.Items = append(out.Items, item)
	}
	var b strings.Builder
	for _, it := range out.Items {
		b.WriteString(fmt.Sprintf("--- node %s ---\n", it.NodeID))
		if it.Error != "" {
			b.WriteString(it.Error)
			b.WriteString("\n")
			continue
		}
		b.WriteString(it.Logs)
		if !strings.HasSuffix(it.Logs, "\n") {
			b.WriteString("\n")
		}
	}
	out.Logs = b.String()
	return out
}

// HealthCheckNode runs a protocol-aware check inside the workload pod.
func HealthCheckNode(ctx context.Context, cfg *rest.Config, client kubernetes.Interface, topologyID, deploymentID, projectID, nodeID string, probe model.RuntimeHealthProbeRequest) model.RuntimeHealthResponse {
	ns := NamespaceFor(strings.TrimSpace(projectID), topologyID, deploymentID)
	nid := strings.TrimSpace(nodeID)
	if nid == "" {
		return model.RuntimeHealthResponse{Status: "failed", Target: "", Message: "node_id is required"}
	}
	pod, err := podNameForNode(ctx, client, ns, nid)
	if err != nil || pod == "" {
		msg := "pod not found"
		if err != nil {
			msg = err.Error()
		}
		return model.RuntimeHealthResponse{Status: "failed", Target: nid, Message: msg}
	}
	pn := model.PlanNode{ID: nid}
	if probe.Image != "" {
		img := probe.Image
		pn.Image = &img
	}
	if probe.PrimaryPort > 0 {
		pn.Ports = []model.RuntimePort{{Port: probe.PrimaryPort, TargetPort: probe.PrimaryPort, Protocol: "TCP"}}
	}
	spec := healthcheck.ProbeSpecFromRequest(probe, &pn)
	execFn := func(argv []string) (string, string, int, error) {
		return podExec(ctx, cfg, client, ns, pod, argv)
	}
	stateFn := func() (bool, string, error) {
		p, err := client.CoreV1().Pods(ns).Get(ctx, pod, metav1.GetOptions{})
		if err != nil {
			return false, "", err
		}
		phase := string(p.Status.Phase)
		return p.Status.Phase == corev1.PodRunning, phase, nil
	}
	return healthcheck.Run(spec, execFn, stateFn)
}

// RunRuntimeTrafficOp runs protocol-aware traffic tests between pods or to an absolute URL.
func RunRuntimeTrafficOp(ctx context.Context, cfg *rest.Config, client kubernetes.Interface, req model.RuntimeTrafficOpRequest) model.RuntimeTrafficOpResponse {
	tid := strings.TrimSpace(req.TopologyID)
	dep := strings.TrimSpace(req.DeploymentID)
	src := strings.TrimSpace(req.SourceNodeID)
	tgt := strings.TrimSpace(req.Target)
	proto := strings.ToLower(strings.TrimSpace(req.Protocol))
	if proto == "" {
		proto = "ping"
	}
	base := model.RuntimeTrafficOpResponse{Source: src, Target: tgt, Protocol: proto}
	if tid == "" || dep == "" || src == "" || tgt == "" {
		base.Status = "failed"
		base.Output = "topology_id, deployment_id, source_node_id, and target are required"
		return base
	}
	ns := NamespaceFor(derefStr(req.ProjectID), tid, dep)

	if strings.HasPrefix(tgt, "http://") || strings.HasPrefix(tgt, "https://") {
		if proto == "ping" {
			base.Status = "unsupported"
			base.Output = "ping to a URL is not supported; use protocol=http"
			return base
		}
		if proto != "http" {
			base.Status = "unsupported"
			base.Output = "protocol must be http for URL targets"
			return base
		}
		pod, err := podNameForNode(ctx, client, ns, src)
		if err != nil || pod == "" {
			base.Status = "failed"
			base.Output = "source pod not found"
			return base
		}
		argv := []string{"wget", "-q", "-O-", "-T", "10", tgt}
		stdout, stderr, code, err := podExec(ctx, cfg, client, ns, pod, argv)
		out := strings.TrimSpace(stdout)
		if stderr != "" {
			if out != "" {
				out += "\n"
			}
			out += strings.TrimSpace(stderr)
		}
		base.Output = out
		if err != nil && code != 0 {
			base.Status = "failed"
			return base
		}
		if code != 0 {
			if trafficutil.HTTPWgetMissing(stderr) || trafficutil.HTTPCurlMissing(stderr) {
				base.Status = "unsupported"
				base.Output = trafficutil.ToolUnavailableMessage
				return base
			}
			base.Status = "failed"
			return base
		}
		base.Status = "passed"
		return base
	}

	if proto != "ping" && proto != "http" && proto != "tcp" && proto != "dns" && proto != "command" {
		base.Status = "unsupported"
		base.Output = "protocol must be ping, http, tcp, dns, or command"
		return base
	}
	tr := model.TrafficRequest{
		Type:         proto,
		TopologyID:   tid,
		SourceNodeID: src,
		TargetNodeID: tgt,
		Count:        req.Count,
		Path:         req.Path,
		Port:         req.Port,
		Command:      req.Command,
		DeploymentID: dep,
		ProjectID:    req.ProjectID,
	}
	resp := RunTrafficTest(ctx, cfg, client, &tr)
	base.Output = strings.TrimSpace(resp.Stdout)
	if resp.Stderr != "" {
		if base.Output != "" {
			base.Output += "\n"
		}
		base.Output += strings.TrimSpace(resp.Stderr)
	}
	if resp.Success {
		base.Status = "passed"
	} else {
		if resp.Error != nil && *resp.Error == trafficutil.ToolUnavailableMessage {
			base.Status = "unsupported"
		} else {
			base.Status = "failed"
		}
		if resp.Error != nil {
			if base.Output != "" {
				base.Output += "\n"
			}
			base.Output += *resp.Error
		}
	}
	return base
}
