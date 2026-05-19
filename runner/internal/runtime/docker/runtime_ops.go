package docker

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	docker "github.com/fsouza/go-dockerclient"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

func clampTail(tail int) int {
	if tail <= 0 {
		return 100
	}
	if tail > 5000 {
		return 5000
	}
	return tail
}

func execInContainer(ctx context.Context, cli *docker.Client, containerID string, argv []string) (stdout, stderr string, exitCode int, err error) {
	exec, err := cli.CreateExec(docker.CreateExecOptions{
		Context:      ctx,
		Container:    containerID,
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          argv,
	})
	if err != nil {
		return "", "", -1, err
	}
	var outBuf, errBuf strings.Builder
	err = cli.StartExec(exec.ID, docker.StartExecOptions{
		Context:      ctx,
		OutputStream: &outBuf,
		ErrorStream:  &errBuf,
	})
	if err != nil {
		return outBuf.String(), errBuf.String(), -1, err
	}
	ins, err := cli.InspectExec(exec.ID)
	if err != nil {
		return outBuf.String(), errBuf.String(), -1, err
	}
	return outBuf.String(), errBuf.String(), ins.ExitCode, nil
}

// RuntimeDeploymentLogs returns recent logs for each node workload on a topology.
func RuntimeDeploymentLogs(ctx context.Context, cli *docker.Client, topologyID, deploymentID string, tail int) model.RuntimeDeploymentLogsResponse {
	tail = clampTail(tail)
	tid := strings.TrimSpace(topologyID)
	out := model.RuntimeDeploymentLogsResponse{
		DeploymentID:    strings.TrimSpace(deploymentID),
		RuntimeProvider: "docker",
		Items:           []model.RuntimeLogsItem{},
	}
	if tid == "" {
		out.Logs = "topology_id is required"
		return out
	}
	ctrs, err := cli.ListContainers(docker.ListContainersOptions{
		Context: ctx,
		All:     true,
		Filters: map[string][]string{
			"label": {
				fmt.Sprintf("cns.topology_id=%s", tid),
				"cns.managed=true",
			},
		},
	})
	if err != nil {
		out.Logs = err.Error()
		return out
	}
	seen := map[string]struct{}{}
	for _, c := range ctrs {
		if c.Labels == nil {
			continue
		}
		nid := strings.TrimSpace(c.Labels["cns.node_id"])
		if nid == "" {
			continue
		}
		if _, ok := seen[nid]; ok {
			continue
		}
		seen[nid] = struct{}{}
		name := strings.TrimSpace(c.Labels["cns.node_name"])
		if name == "" && len(c.Names) > 0 {
			name = strings.TrimPrefix(c.Names[0], "/")
		}
		logs, err := LogsForNode(ctx, cli, tid, nid, tail)
		item := model.RuntimeLogsItem{NodeID: nid, ServiceID: nid, Name: name}
		if err != nil {
			item.Error = err.Error()
		} else {
			item.Logs = logs
		}
		out.Items = append(out.Items, item)
	}
	var b strings.Builder
	for _, it := range out.Items {
		b.WriteString(fmt.Sprintf("--- node %s (%s) ---\n", it.NodeID, it.Name))
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

// HealthCheckNode runs an HTTP GET from inside the container via wget (busybox/alpine).
func HealthCheckNode(ctx context.Context, cli *docker.Client, topologyID, nodeID string, port int, path string) model.RuntimeHealthResponse {
	tid := strings.TrimSpace(topologyID)
	nid := strings.TrimSpace(nodeID)
	if port <= 0 {
		port = 80
	}
	if path == "" {
		path = "/"
	}
	if !strings.HasPrefix(path, "/") {
		path = "/" + path
	}
	target := fmt.Sprintf("http://127.0.0.1:%d%s", port, path)
	if tid == "" || nid == "" {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: "topology_id and node_id are required"}
	}
	cid, err := findContainerID(ctx, cli, tid, nid)
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	if cid == "" {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: "container not found for node"}
	}
	argv := []string{"wget", "-q", "-O-", "-T", "8", target}
	stdout, stderr, code, err := execInContainer(ctx, cli, cid, argv)
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	if code != 0 {
		msg := strings.TrimSpace(stderr)
		if msg == "" {
			msg = fmt.Sprintf("wget exit %d", code)
		}
		if trafficutil.HTTPWgetMissing(stderr) || trafficutil.HTTPWgetMissing(msg) {
			return model.RuntimeHealthResponse{
				Status:  "unsupported",
				Target:  target,
				Message: "HTTP check tool is missing in runtime container.",
			}
		}
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: msg}
	}
	_ = stdout
	return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: "HTTP check succeeded inside container"}
}

// RunRuntimeTrafficOp runs ping/http between nodes or http to an absolute URL from the source container.
func RunRuntimeTrafficOp(ctx context.Context, cli *docker.Client, req model.RuntimeTrafficOpRequest) model.RuntimeTrafficOpResponse {
	tid := strings.TrimSpace(req.TopologyID)
	src := strings.TrimSpace(req.SourceNodeID)
	tgt := strings.TrimSpace(req.Target)
	proto := strings.ToLower(strings.TrimSpace(req.Protocol))
	if proto == "" {
		proto = "ping"
	}
	base := model.RuntimeTrafficOpResponse{
		Source: src, Target: tgt, Protocol: proto,
	}
	if tid == "" || src == "" || tgt == "" {
		base.Status = "failed"
		base.Output = "topology_id, source_node_id, and target are required (topology_id may be supplied via query string)"
		return base
	}
	if strings.HasPrefix(tgt, "http://") || strings.HasPrefix(tgt, "https://") {
		if proto == "ping" {
			base.Status = "unsupported"
			base.Output = "ping to a URL is not supported; use protocol=http"
			return base
		}
		if proto != "http" {
			base.Status = "unsupported"
			base.Output = "protocol must be http or ping"
			return base
		}
		cid, err := findContainerID(ctx, cli, tid, src)
		if err != nil || cid == "" {
			base.Status = "failed"
			base.Output = "source container not found"
			if err != nil {
				base.Output = err.Error()
			}
			return base
		}
		argv := []string{"wget", "-q", "-O-", "-T", "10", tgt}
		stdout, stderr, code, err := execInContainer(ctx, cli, cid, argv)
		out := stdout
		if stderr != "" {
			if out != "" {
				out += "\n"
			}
			out += stderr
		}
		base.Output = strings.TrimSpace(out)
		if err != nil {
			base.Status = "failed"
			return base
		}
		if code != 0 {
			base.Status = "failed"
			if trafficutil.HTTPWgetMissing(stderr) {
				base.Output = strings.TrimSpace("HTTP test tool is missing in client image\n" + base.Output)
			}
			return base
		}
		base.Status = "passed"
		return base
	}
	// Target is a peer node id.
	tt := "ping"
	if proto == "http" {
		tt = "http"
	} else if proto != "ping" {
		base.Status = "unsupported"
		base.Output = "protocol must be http or ping"
		return base
	}
	tr := model.TrafficRequest{
		Type:           tt,
		TopologyID:     tid,
		SourceNodeID:   src,
		TargetNodeID:   tgt,
		Count:          req.Count,
		Path:           req.Path,
		Port:           req.Port,
		DeploymentID:   req.DeploymentID,
		ProjectID:      req.ProjectID,
	}
	resp := RunTrafficTest(ctx, cli, &tr)
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
		base.Status = "failed"
		if resp.Error != nil {
			if base.Output != "" {
				base.Output += "\n"
			}
			base.Output += *resp.Error
		}
	}
	return base
}

// LogsForContainerName fetches logs when the container is addressed by engine name or id.
func LogsForContainerName(ctx context.Context, cli *docker.Client, nameOrID string, tail int) (string, error) {
	tail = clampTail(tail)
	id := strings.TrimSpace(nameOrID)
	if id == "" {
		return "", fmt.Errorf("container name or id is required")
	}
	buf := new(strings.Builder)
	err := cli.Logs(docker.LogsOptions{
		Context:      ctx,
		Container:    id,
		OutputStream: buf,
		ErrorStream:  buf,
		Stdout:       true,
		Stderr:       true,
		Tail:         strconv.Itoa(tail),
		Follow:       false,
	})
	if err != nil {
		return "", err
	}
	return buf.String(), nil
}
