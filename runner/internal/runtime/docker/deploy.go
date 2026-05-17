package docker

import (
	"context"
	"fmt"
	"net"
	"regexp"
	"strings"

	docker "github.com/fsouza/go-dockerclient"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func TopologyNetworkName(topologyID string) string {
	s := strings.ReplaceAll(topologyID, "-", "")
	if len(s) > 12 {
		s = s[:12]
	}
	return "cns-topology-" + s
}

func ContainerName(nodeID, nodeName string) string {
	short := strings.ReplaceAll(nodeID, "-", "")
	if len(short) > 12 {
		short = short[:12]
	}
	re := regexp.MustCompile(`[^a-zA-Z0-9_.-]+`)
	safe := strings.Trim(re.ReplaceAllString(nodeName, "-"), "-")
	if len(safe) > 40 {
		safe = safe[:40]
	}
	if safe == "" {
		safe = "node"
	}
	return fmt.Sprintf("cns-node-%s-%s", short, safe)
}

func baseLabels(topologyID string) map[string]string {
	return map[string]string{
		"cns.project":     "cloud-networking-studio",
		"cns.topology_id": topologyID,
		"cns.managed":     "true",
	}
}

func nodeLabels(topologyID, nodeID, forwardingRole string) map[string]string {
	m := baseLabels(topologyID)
	m["cns.node_id"] = nodeID
	if forwardingRole != "" {
		m["cns.forwarding_role"] = forwardingRole
	}
	return m
}

func resolveImage(img *string) string {
	if img == nil {
		return "alpine:latest"
	}
	s := strings.TrimSpace(*img)
	if s == "" {
		return "alpine:latest"
	}
	return s
}

func defaultCommand(image string) []string {
	il := strings.ToLower(image)
	if strings.Contains(il, "busybox") {
		return []string{"sh", "-c", "mkdir -p /www && printf 'ok\\n' >/www/index.html && exec httpd -f -p 80 -h /www"}
	}
	if strings.Contains(il, "nginx") {
		return nil
	}
	return []string{"sleep", "infinity"}
}

func ipamFromSubnet(cidr *string) *docker.IPAMOptions {
	if cidr == nil {
		return nil
	}
	s := strings.TrimSpace(*cidr)
	if s == "" {
		return nil
	}
	_, ipnet, err := net.ParseCIDR(s)
	if err != nil {
		return nil
	}
	if ipnet.IP.To4() == nil {
		return nil
	}
	base := ipnet.IP.Mask(ipnet.Mask).To4()
	gw := make(net.IP, len(base))
	copy(gw, base)
	gw[len(gw)-1]++ // first host address (matches Python network_address + 1 for typical /24 labs)
	return &docker.IPAMOptions{
		Driver: "default",
		Config: []docker.IPAMConfig{{
			Subnet:  ipnet.String(),
			Gateway: gw.String(),
		}},
	}
}

func removeNetworkIfExists(cli *docker.Client, name string) {
	nets, err := cli.ListNetworks()
	if err != nil {
		return
	}
	for _, n := range nets {
		if n.Name == name {
			_ = cli.RemoveNetwork(n.ID)
			return
		}
	}
}

func removeContainerIfExists(cli *docker.Client, name string) {
	ctr, err := cli.InspectContainer(name)
	if err != nil {
		return
	}
	_ = cli.StopContainer(ctr.ID, 15)
	_ = cli.RemoveContainer(docker.RemoveContainerOptions{ID: ctr.ID, Force: true})
}

// DeploySimple mirrors the non-segmented Python Docker path (single bridge + labeled containers).
func DeploySimple(ctx context.Context, cli *docker.Client, req *model.DeploymentRequest) model.DeploymentResponse {
	ev := func(level, msg string) model.Event {
		return model.Event{Level: level, Message: msg}
	}
	var events []model.Event
	if req.SegmentedNetworks {
		msg := "segmented multinet topologies are not supported by the Go runner yet; use RUNTIME_EXECUTOR=python"
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: []model.Event{
			ev("error", msg),
		}, Error: &msg}
	}
	if strings.TrimSpace(req.TopologyID) == "" {
		msg := "topology_id is required"
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: []model.Event{ev("error", msg)}, Error: &msg}
	}

	netName := TopologyNetworkName(req.TopologyID)
	events = append(events, ev("info", "Go runner: Docker provider selected"))
	events = append(events, ev("info", fmt.Sprintf("Creating Docker network: %s", netName)))

	removeNetworkIfExists(cli, netName)

	ipam := ipamFromSubnet(req.SubnetCIDR)
	_, netErr := cli.CreateNetwork(docker.CreateNetworkOptions{
		Context:        ctx,
		Name:           netName,
		Driver:         "bridge",
		IPAM:           ipam,
		Labels:         baseLabels(req.TopologyID),
		CheckDuplicate: true,
	})
	if netErr != nil {
		msg := fmt.Sprintf("Docker network creation failed: %v", netErr)
		events = append(events, ev("error", msg))
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
	}
	extra := ""
	if req.SubnetCIDR != nil && strings.TrimSpace(*req.SubnetCIDR) != "" {
		extra = fmt.Sprintf(" (subnet %s)", strings.TrimSpace(*req.SubnetCIDR))
	}
	events = append(events, ev("info", fmt.Sprintf("Docker network created: %s%s", netName, extra)))

	for _, pn := range req.Nodes {
		cname := ContainerName(pn.ID, pn.Name)
		imageRef := resolveImage(pn.Image)
		role := "leaf"
		if strings.EqualFold(pn.NodeType, "router") {
			role = "segment_router"
		}
		labels := nodeLabels(req.TopologyID, pn.ID, role)

		removeContainerIfExists(cli, cname)

		cmd := defaultCommand(imageRef)
		repo, tag := docker.ParseRepositoryTag(imageRef)
		if tag == "" {
			tag = "latest"
		}
		_ = cli.PullImage(docker.PullImageOptions{Context: ctx, Repository: repo, Tag: tag}, docker.AuthConfiguration{})

		var staticIP string
		if pn.IPAddress != nil {
			staticIP = strings.TrimSpace(*pn.IPAddress)
		}
		ep := &docker.EndpointConfig{}
		if staticIP != "" {
			ep.IPAMConfig = &docker.EndpointIPAMConfig{IPv4Address: staticIP}
		}

		host := &docker.HostConfig{CapAdd: []string{"NET_ADMIN"}}
		ctr, err := cli.CreateContainer(docker.CreateContainerOptions{
			Context: ctx,
			Name:    cname,
			Config: &docker.Config{
				Image:  imageRef,
				Labels: labels,
				Cmd:    cmd,
			},
			HostConfig: host,
			NetworkingConfig: &docker.NetworkingConfig{
				EndpointsConfig: map[string]*docker.EndpointConfig{
					netName: ep,
				},
			},
		})
		if err != nil {
			msg := fmt.Sprintf("container create failed (%s): %v", cname, err)
			events = append(events, ev("error", msg))
			_ = DestroyTopology(ctx, cli, req.TopologyID)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		if err := cli.StartContainer(ctr.ID, nil); err != nil {
			msg := fmt.Sprintf("container start failed (%s): %v", cname, err)
			events = append(events, ev("error", msg))
			_ = DestroyTopology(ctx, cli, req.TopologyID)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		events = append(events, ev("info", fmt.Sprintf("Container started: %s", cname)))
	}

	events = append(events, ev("info", "Deployment completed successfully"))
	return model.DeploymentResponse{Status: "succeeded", RuntimeProvider: "docker", Events: events}
}

// DestroyTopology removes labeled containers and CNS networks for a topology (best-effort).
func DestroyTopology(ctx context.Context, cli *docker.Client, topologyID string) []model.Event {
	var events []model.Event
	ev := func(level, msg string) model.Event { return model.Event{Level: level, Message: msg} }
	tid := strings.TrimSpace(topologyID)
	ctrs, err := cli.ListContainers(docker.ListContainersOptions{
		Context: ctx,
		All:     true,
		Filters: map[string][]string{"label": {fmt.Sprintf("cns.topology_id=%s", tid)}},
	})
	if err == nil {
		for _, c := range ctrs {
			id := c.ID
			name := c.Names[0]
			if strings.HasPrefix(name, "/") {
				name = name[1:]
			}
			events = append(events, ev("info", fmt.Sprintf("Stopping container: %s", name)))
			_ = cli.StopContainer(id, 15)
			_ = cli.RemoveContainer(docker.RemoveContainerOptions{Context: ctx, ID: id, Force: true})
			events = append(events, ev("info", fmt.Sprintf("Removed container: %s", name)))
		}
	}

	nets, err := cli.ListNetworks()
	if err == nil {
		for _, n := range nets {
			if n.Labels == nil {
				continue
			}
			if n.Labels["cns.topology_id"] == tid && n.Labels["cns.managed"] == "true" {
				events = append(events, ev("info", fmt.Sprintf("Removing network: %s", n.Name)))
				_ = cli.RemoveNetwork(n.ID)
			}
		}
	}
	events = append(events, ev("info", "Runtime resources destroyed"))
	return events
}
