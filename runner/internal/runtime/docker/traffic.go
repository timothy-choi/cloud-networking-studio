package docker

import (
	"context"
	"fmt"
	"strings"

	docker "github.com/fsouza/go-dockerclient"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

// RunTrafficTest executes ping or wget-based HTTP from source container to target IP (minimal parity with Python).
func RunTrafficTest(ctx context.Context, cli *docker.Client, req *model.TrafficRequest) model.TrafficResponse {
	tid := strings.TrimSpace(req.TopologyID)
	src := strings.TrimSpace(req.SourceNodeID)
	tgt := strings.TrimSpace(req.TargetNodeID)
	if tid == "" || src == "" || tgt == "" {
		msg := "topology_id, source_node_id, and target_node_id are required"
		return model.TrafficResponse{ExitCode: 1, Success: false, Error: &msg}
	}
	srcID, err := findContainerID(ctx, cli, tid, src)
	if err != nil {
		msg := err.Error()
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}
	if srcID == "" {
		msg := "source container not found"
		return model.TrafficResponse{ExitCode: 127, Success: false, Stderr: msg, Error: &msg}
	}
	tgtIP, err := targetIPv4(ctx, cli, tid, tgt)
	if err != nil || tgtIP == "" {
		msg := "could not resolve target IPv4 on topology network"
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
	case "tcp":
		port := req.Port
		if port <= 0 {
			port = 80
		}
		argv = []string{"sh", "-c", fmt.Sprintf("nc -z -w 3 %s %d", tgtIP, port)}
	case "dns":
		host := strings.TrimSpace(req.TargetNodeID)
		if host == "" {
			host = tgtIP
		}
		argv = []string{"nslookup", host}
	case "command":
		if len(req.Command) > 0 {
			argv = append([]string{}, req.Command...)
		} else {
			msg := "command protocol requires command argv"
			return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
		}
	default:
		msg := "type must be ping, http, tcp, dns, or command"
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}

	exec, err := cli.CreateExec(docker.CreateExecOptions{
		Context:      ctx,
		Container:    srcID,
		AttachStdout: true,
		AttachStderr: true,
		Cmd:          argv,
	})
	if err != nil {
		msg := err.Error()
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}
	var outBuf, errBuf strings.Builder
	err = cli.StartExec(exec.ID, docker.StartExecOptions{
		Context:      ctx,
		OutputStream: &outBuf,
		ErrorStream:  &errBuf,
	})
	if err != nil {
		msg := err.Error()
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}
	ins, err := cli.InspectExec(exec.ID)
	if err != nil {
		msg := err.Error()
		return model.TrafficResponse{ExitCode: 1, Success: false, Stderr: msg, Error: &msg}
	}
	exit := ins.ExitCode
	stderr := errBuf.String()
	ok := exit == 0
	var errPtr *string
	comout := outBuf.String()
	combined := strings.TrimSpace(stderr + "\n" + comout)
	if !ok {
		if tt == "http" && trafficutil.HTTPWgetMissing(stderr) {
			msg := trafficutil.ToolUnavailableMessage
			errPtr = &msg
		} else if tt == "ping" && trafficutil.PingMissing(combined) {
			msg := trafficutil.ToolUnavailableMessage
			errPtr = &msg
		} else if (tt == "tcp" && trafficutil.NcMissing(combined)) || (tt == "dns" && trafficutil.DigMissing(combined) && trafficutil.AnyToolMissing(combined, "nslookup")) {
			msg := trafficutil.ToolUnavailableMessage
			errPtr = &msg
		} else if tt == "command" && len(argv) > 0 && trafficutil.AnyToolMissing(combined, argv[0]) {
			msg := trafficutil.ToolUnavailableMessage
			errPtr = &msg
		}
	}
	return model.TrafficResponse{
		ExitCode: exit,
		Stdout:   outBuf.String(),
		Stderr:   stderr,
		Success:  ok,
		Error:    errPtr,
	}
}

func findContainerID(ctx context.Context, cli *docker.Client, topologyID, nodeID string) (string, error) {
	ctrs, err := cli.ListContainers(docker.ListContainersOptions{
		Context: ctx,
		All:     true,
		Filters: map[string][]string{
			"label": {
				fmt.Sprintf("cns.topology_id=%s", topologyID),
				fmt.Sprintf("cns.node_id=%s", nodeID),
			},
		},
	})
	if err != nil {
		return "", err
	}
	if len(ctrs) == 0 {
		return "", nil
	}
	return ctrs[0].ID, nil
}

func targetIPv4(ctx context.Context, cli *docker.Client, topologyID, nodeID string) (string, error) {
	id, err := findContainerID(ctx, cli, topologyID, nodeID)
	if err != nil || id == "" {
		return "", err
	}
	ins, err := cli.InspectContainerWithOptions(docker.InspectContainerOptions{Context: ctx, ID: id})
	if err != nil {
		return "", err
	}
	netName := TopologyNetworkName(topologyID)
	if ins.NetworkSettings != nil && ins.NetworkSettings.Networks != nil {
		if ep, ok := ins.NetworkSettings.Networks[netName]; ok && ep.IPAddress != "" {
			return ep.IPAddress, nil
		}
		for _, ep := range ins.NetworkSettings.Networks {
			if ep.IPAddress != "" && !strings.HasPrefix(ep.IPAddress, "172.17.") {
				return ep.IPAddress, nil
			}
		}
	}
	return "", fmt.Errorf("no IP")
}
