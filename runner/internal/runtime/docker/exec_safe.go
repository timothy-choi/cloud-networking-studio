package docker

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	docker "github.com/fsouza/go-dockerclient"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

// SafeExecWorkload runs argv inside the container for topology nodeID with a deadline.
func SafeExecWorkload(
	ctx context.Context,
	cli *docker.Client,
	topologyID, nodeID string,
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

	cid, err := findContainerID(ctx, cli, topologyID, nodeID)
	if err != nil || cid == "" {
		return "", "", -1, "failed", ""
	}
	out, errOut, code, err := execInContainer(ctx, cli, cid, argv)
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
	return strings.TrimSpace(out), strings.TrimSpace(errOut), code, "succeeded", ""
}

// RestartWorkload restarts the container for a topology node.
func RestartWorkload(ctx context.Context, cli *docker.Client, topologyID, nodeID string) error {
	cid, err := findContainerID(ctx, cli, topologyID, nodeID)
	if err != nil {
		return err
	}
	if cid == "" {
		return fmt.Errorf("container not found")
	}
	return cli.RestartContainer(cid, uint(30))
}
