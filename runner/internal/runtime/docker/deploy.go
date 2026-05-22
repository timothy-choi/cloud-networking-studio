package docker

import (
	"context"
	"encoding/json"
	"errors"
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

func cnsLabels(topologyID, deploymentID string, projectID *string) map[string]string {
	m := map[string]string{
		"app":             "cloud-networking-studio",
		"cns.topology_id": strings.TrimSpace(topologyID),
		"cns.managed":     "true",
	}
	if d := strings.TrimSpace(deploymentID); d != "" {
		m["cns.deployment_id"] = d
	}
	if projectID != nil {
		if p := strings.TrimSpace(*projectID); p != "" {
			m["cns.project_id"] = p
		}
	}
	return m
}

func nodeLabels(req *model.DeploymentRequest, nodeID, forwardingRole string) map[string]string {
	m := cnsLabels(req.TopologyID, req.DeploymentID, req.ProjectID)
	m["cns.node_id"] = strings.TrimSpace(nodeID)
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

func enrichContainerNetworkMeta(
	ctx context.Context,
	cli *docker.Client,
	containerID string,
	netName string,
	intendedIP string,
	meta map[string]string,
) {
	if meta == nil {
		return
	}
	if s := strings.TrimSpace(intendedIP); s != "" {
		meta["intended_ip"] = s
	}
	ins, err := cli.InspectContainerWithOptions(docker.InspectContainerOptions{Context: ctx, ID: containerID})
	if err != nil || ins.NetworkSettings == nil {
		return
	}
	nets := ins.NetworkSettings.Networks
	if ent, ok := nets[netName]; ok {
		if ip := strings.TrimSpace(ent.IPAddress); ip != "" {
			meta["actual_runtime_ip"] = ip
			return
		}
	}
	for _, ent := range nets {
		if ip := strings.TrimSpace(ent.IPAddress); ip != "" {
			meta["actual_runtime_ip"] = ip
			return
		}
	}
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

func resolveForwardingRole(pn model.PlanNode) string {
	if pn.RoleLabel != nil {
		if s := strings.TrimSpace(*pn.RoleLabel); s != "" {
			return s
		}
	}
	if strings.EqualFold(pn.NodeType, "router") {
		return "segment_router"
	}
	return "leaf"
}

func resolveContainerCommand(pn model.PlanNode, imageRef string) []string {
	if len(pn.Command) > 0 {
		return pn.Command
	}
	if strings.EqualFold(pn.NodeType, "router") {
		return []string{"sleep", "infinity"}
	}
	return defaultCommand(imageRef)
}

func effectivePorts(pn model.PlanNode) []model.RuntimePort {
	if len(pn.Ports) > 0 {
		out := make([]model.RuntimePort, 0, len(pn.Ports))
		for _, p := range pn.Ports {
			tp := p.TargetPort
			if tp == 0 {
				tp = p.Port
			}
			proto := strings.TrimSpace(p.Protocol)
			if proto == "" {
				proto = "TCP"
			}
			out = append(out, model.RuntimePort{Port: p.Port, TargetPort: tp, Protocol: strings.ToUpper(proto)})
		}
		return out
	}
	return []model.RuntimePort{{Port: 80, TargetPort: 80, Protocol: "TCP"}}
}

func primaryPort(pn model.PlanNode) int {
	ports := effectivePorts(pn)
	if len(ports) == 0 {
		return 80
	}
	return ports[0].Port
}

func envSliceFromPlanNode(pn model.PlanNode) []string {
	if len(pn.Env) == 0 {
		return nil
	}
	out := make([]string, 0, len(pn.Env))
	for k, v := range pn.Env {
		k = strings.TrimSpace(k)
		if k == "" {
			continue
		}
		out = append(out, fmt.Sprintf("%s=%s", k, v))
	}
	return out
}

func planNodeRuntimeMeta(pn model.PlanNode, imageRef string, cmd []string) map[string]string {
	meta := map[string]string{}
	if pn.RoleLabel != nil {
		if s := strings.TrimSpace(*pn.RoleLabel); s != "" {
			meta["role_label"] = s
		}
	}
	if s := strings.TrimSpace(imageRef); s != "" {
		meta["image"] = s
	}
	if len(cmd) > 0 {
		meta["command"] = strings.Join(cmd, " ")
	}
	if pn.Description != nil {
		if s := strings.TrimSpace(*pn.Description); s != "" {
			meta["description"] = s
		}
	}
	if pn.TerminalEnabled != nil {
		if *pn.TerminalEnabled {
			meta["terminal_enabled"] = "true"
		} else {
			meta["terminal_enabled"] = "false"
		}
	}
	if pn.HealthCheck != nil {
		if path, ok := pn.HealthCheck["path"]; ok {
			meta["health_check_path"] = fmt.Sprint(path)
		}
		if port, ok := pn.HealthCheck["port"]; ok {
			meta["health_check_port"] = fmt.Sprint(port)
		}
	}
	if pn.IPAddress != nil {
		if s := strings.TrimSpace(*pn.IPAddress); s != "" {
			meta["intended_ip"] = s
		}
	}
	if len(pn.Env) > 0 {
		if b, err := json.Marshal(pn.Env); err == nil {
			meta["env"] = string(b)
		}
	}
	return meta
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

	intentMode := isIntentMode(req.NetworkAllocationMode)
	if intentMode {
		events = append(events, ev("info", "Network allocation mode: intent"))
	} else {
		events = append(events, ev("info", "Network allocation mode: managed"))
	}

	subnetStr := req.SubnetCIDR
	if req.SubnetCIDR != nil && strings.TrimSpace(*req.SubnetCIDR) != "" {
		chosen, note, err := resolveBridgeSubnet(cli, strings.TrimSpace(*req.SubnetCIDR), intentMode)
		if err != nil {
			if errors.Is(err, errSubnetOverlap) {
				msg := intentSubnetOverlapMessage
				if !intentMode {
					msg = dockerSubnetOverlapMessage
				}
				events = append(events, ev("error", msg))
				return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
			}
			msg := fmt.Sprintf("Docker subnet resolution failed: %v", err)
			events = append(events, ev("error", msg))
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		if note != "" {
			events = append(events, ev("info", note))
		}
		if chosen != "" {
			cs := chosen
			subnetStr = &cs
		}
	}

	ipam := ipamFromSubnet(subnetStr)
	_, netErr := cli.CreateNetwork(docker.CreateNetworkOptions{
		Context:        ctx,
		Name:           netName,
		Driver:         "bridge",
		IPAM:           ipam,
		Labels:         cnsLabels(req.TopologyID, req.DeploymentID, req.ProjectID),
		CheckDuplicate: true,
	})
	if netErr != nil {
		low := strings.ToLower(netErr.Error())
		if strings.Contains(low, "overlap") || strings.Contains(low, "pool overlaps") {
			msg := intentSubnetOverlapMessage
			if !intentMode {
				msg = dockerSubnetOverlapMessage
			}
			events = append(events, ev("error", msg))
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		msg := fmt.Sprintf("Docker network creation failed: %v", netErr)
		events = append(events, ev("error", msg))
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
	}
	extra := ""
	if subnetStr != nil && strings.TrimSpace(*subnetStr) != "" {
		extra = fmt.Sprintf(" (subnet %s)", strings.TrimSpace(*subnetStr))
	}
	events = append(events, ev("info", fmt.Sprintf("Docker network created: %s%s", netName, extra)))

	var accessResources []model.RuntimeAccessResource
	accessResources = append(accessResources, model.RuntimeAccessResource{
		Type:               "network",
		Name:               netName,
		RuntimeName:        netName,
		Status:             "active",
		NamespaceOrNetwork: netName,
		Metadata: map[string]string{
			"topology_id": strings.TrimSpace(req.TopologyID),
		},
	})

	for _, pn := range req.Nodes {
		cname := ContainerName(pn.ID, pn.Name)
		imageRef := resolveImage(pn.Image)
		role := resolveForwardingRole(pn)
		labels := nodeLabels(req, pn.ID, role)

		removeContainerIfExists(cli, cname)

		cmd := resolveContainerCommand(pn, imageRef)
		ports := effectivePorts(pn)
		portNum := primaryPort(pn)
		env := envSliceFromPlanNode(pn)
		repo, tag := docker.ParseRepositoryTag(imageRef)
		if tag == "" {
			tag = "latest"
		}
		_ = cli.PullImage(docker.PullImageOptions{Context: ctx, Repository: repo, Tag: tag}, docker.AuthConfiguration{})

		var staticIP string
		if intentMode && pn.IPAddress != nil {
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
				Env:    env,
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
			_ = DestroyDeployment(ctx, cli, req.DeploymentID, req.TopologyID)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		if err := cli.StartContainer(ctr.ID, nil); err != nil {
			msg := fmt.Sprintf("container start failed (%s): %v", cname, err)
			events = append(events, ev("error", msg))
			_ = DestroyDeployment(ctx, cli, req.DeploymentID, req.TopologyID)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "docker", Events: events, Error: &msg}
		}
		events = append(events, ev("info", fmt.Sprintf("Container started: %s", cname)))
		nid := strings.TrimSpace(pn.ID)
		internal := fmt.Sprintf("http://%s:%d", cname, portNum)
		metaBase := planNodeRuntimeMeta(pn, imageRef, cmd)
		metaBase["container_id"] = ctr.ID
		if ins, err := cli.InspectContainerWithOptions(docker.InspectContainerOptions{Context: ctx, ID: ctr.ID}); err == nil && ins.NetworkSettings != nil && ins.NetworkSettings.Ports != nil {
			var parts []string
			for port, bindings := range ins.NetworkSettings.Ports {
				for _, b := range bindings {
					if b.HostPort != "" {
						hip := b.HostIP
						if hip == "" || hip == "0.0.0.0" {
							hip = "127.0.0.1"
						}
						parts = append(parts, fmt.Sprintf("%s:%s->%s", hip, b.HostPort, port))
					}
				}
			}
			if len(parts) > 0 {
				metaBase["host_port_bindings"] = strings.Join(parts, ",")
			} else {
				metaBase["external_access"] = "manual_port_forward_required"
			}
		} else {
			metaBase["external_access"] = "manual_port_forward_required"
		}
		intendedMeta := ""
		if pn.IPAddress != nil {
			intendedMeta = strings.TrimSpace(*pn.IPAddress)
		}
		enrichContainerNetworkMeta(ctx, cli, ctr.ID, netName, intendedMeta, metaBase)
		accessResources = append(accessResources, model.RuntimeAccessResource{
			Type:               "node",
			NodeID:             nid,
			Name:               strings.TrimSpace(pn.Name),
			RuntimeName:        cname,
			Status:             "running",
			NamespaceOrNetwork: netName,
			Ports:              ports,
			InternalURL:        internal,
			Metadata:           metaBase,
		})
		accessResources = append(accessResources, model.RuntimeAccessResource{
			Type:               "service",
			ServiceID:          nid,
			Name:               strings.TrimSpace(pn.Name),
			RuntimeName:        cname,
			Status:             "running",
			NamespaceOrNetwork: netName,
			Ports:              ports,
			InternalURL:        internal,
			Metadata:           metaBase,
		})
	}

	events = append(events, ev("info", "Deployment completed successfully"))
	ra := &model.RuntimeAccess{
		DeploymentID:       strings.TrimSpace(req.DeploymentID),
		TopologyID:         strings.TrimSpace(req.TopologyID),
		Status:             "running",
		RuntimeProvider:    "docker",
		NamespaceOrNetwork: netName,
		Resources:          accessResources,
	}
	return model.DeploymentResponse{
		Status:          "succeeded",
		RuntimeProvider: "docker",
		Events:          events,
		RuntimeAccess:   ra,
	}
}

// DestroyTopology is legacy cleanup by topology id only (no deployment label filter).
func DestroyTopology(ctx context.Context, cli *docker.Client, topologyID string) []model.Event {
	return DestroyDeployment(ctx, cli, "", topologyID)
}

// DestroyDeployment tears down containers and networks labeled for a deployment and/or topology (best-effort).
func DestroyDeployment(ctx context.Context, cli *docker.Client, deploymentID, topologyID string) []model.Event {
	var events []model.Event
	ev := func(level, msg string) model.Event { return model.Event{Level: level, Message: msg} }
	did := strings.TrimSpace(deploymentID)
	tid := strings.TrimSpace(topologyID)

	seen := map[string]struct{}{}
	filters := []map[string][]string{}
	if did != "" {
		filters = append(filters, map[string][]string{"label": {fmt.Sprintf("cns.deployment_id=%s", did)}})
	}
	if tid != "" {
		filters = append(filters, map[string][]string{"label": {fmt.Sprintf("cns.topology_id=%s", tid)}})
	}
	for _, flt := range filters {
		ctrs, err := cli.ListContainers(docker.ListContainersOptions{
			Context: ctx,
			All:     true,
			Filters: flt,
		})
		if err != nil {
			continue
		}
		for _, c := range ctrs {
			if _, ok := seen[c.ID]; ok {
				continue
			}
			seen[c.ID] = struct{}{}
			name := ""
			if len(c.Names) > 0 {
				name = c.Names[0]
				if strings.HasPrefix(name, "/") {
					name = name[1:]
				}
			}
			events = append(events, ev("info", fmt.Sprintf("Stopping container: %s", name)))
			_ = cli.StopContainer(c.ID, 15)
			_ = cli.RemoveContainer(docker.RemoveContainerOptions{Context: ctx, ID: c.ID, Force: true})
			events = append(events, ev("info", fmt.Sprintf("Removed container: %s", name)))
		}
	}

	netSeen := map[string]struct{}{}
	nets, err := cli.ListNetworks()
	if err == nil {
		for _, n := range nets {
			if n.Labels == nil {
				continue
			}
			rm := false
			if did != "" && n.Labels["cns.deployment_id"] == did {
				rm = true
			}
			if tid != "" && n.Labels["cns.topology_id"] == tid && n.Labels["cns.managed"] == "true" {
				rm = true
			}
			if !rm {
				continue
			}
			if _, ok := netSeen[n.ID]; ok {
				continue
			}
			netSeen[n.ID] = struct{}{}
			events = append(events, ev("info", fmt.Sprintf("Removing network: %s", n.Name)))
			_ = cli.RemoveNetwork(n.ID)
		}
	}
	events = append(events, ev("info", "Runtime resources destroyed"))
	return events
}
