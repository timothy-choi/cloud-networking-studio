package docker

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	docker "github.com/fsouza/go-dockerclient"
)

// NewClient connects to Docker using DOCKER_HOST or the default local socket.
func NewClient() (*docker.Client, error) {
	return docker.NewClientFromEnv()
}

// LogsForNode returns combined stdout/stderr for the managed container (tail lines).
func LogsForNode(ctx context.Context, cli *docker.Client, topologyID, nodeID string, tail int) (string, error) {
	if tail <= 0 {
		tail = 100
	}
	if tail > 5000 {
		tail = 5000
	}
	tid := strings.TrimSpace(topologyID)
	nid := strings.TrimSpace(nodeID)
	ctrs, err := cli.ListContainers(docker.ListContainersOptions{
		Context: ctx,
		All:     true,
		Filters: map[string][]string{
			"label": {
				fmt.Sprintf("cns.topology_id=%s", tid),
				fmt.Sprintf("cns.node_id=%s", nid),
			},
		},
	})
	if err != nil {
		return "", err
	}
	if len(ctrs) == 0 {
		return "", fmt.Errorf("no container for topology %s node %s", tid, nid)
	}
	id := ctrs[0].ID
	buf := new(strings.Builder)
	err = cli.Logs(docker.LogsOptions{
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
