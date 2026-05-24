package nodeconfig

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

func DefaultImageForNodeType(nodeType string) string {
	switch strings.ToLower(strings.TrimSpace(nodeType)) {
	case "generic", "service":
		return "nginx:alpine"
	default:
		return "alpine:latest"
	}
}

// ResolveImage applies backward-compatible defaults for legacy nodes with nil image.
// Explicit blank strings are rejected so the API can return validation errors.
func ResolveImage(img *string, nodeType string) (string, error) {
	if img == nil {
		return DefaultImageForNodeType(nodeType), nil
	}
	s := strings.TrimSpace(*img)
	if s == "" {
		return "", fmt.Errorf("Node image is required")
	}
	return s, nil
}

func DefaultCommand(image string) []string {
	il := strings.ToLower(image)
	if strings.Contains(il, "busybox") {
		return []string{"sh", "-c", "mkdir -p /www && printf 'ok\\n' >/www/index.html && exec httpd -f -p 80 -h /www"}
	}
	if strings.Contains(il, "nginx") {
		return nil
	}
	return []string{"sleep", "infinity"}
}

func ResolveForwardingRole(pn model.PlanNode) string {
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

func ResolveContainerCommand(pn model.PlanNode, imageRef string) []string {
	if len(pn.Command) > 0 {
		return pn.Command
	}
	if strings.EqualFold(pn.NodeType, "router") {
		return []string{"sleep", "infinity"}
	}
	return DefaultCommand(imageRef)
}

func EffectivePorts(pn model.PlanNode) []model.RuntimePort {
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

func PrimaryPort(pn model.PlanNode) int {
	ports := EffectivePorts(pn)
	if len(ports) == 0 {
		return 80
	}
	return ports[0].Port
}

func EnvSliceFromPlanNode(pn model.PlanNode) []string {
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

func PlanNodeRuntimeMeta(pn model.PlanNode, imageRef string, cmd []string) map[string]string {
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

func HealthCheckPath(pn model.PlanNode) string {
	if pn.HealthCheck == nil {
		return ""
	}
	if path, ok := pn.HealthCheck["path"]; ok {
		return strings.TrimSpace(fmt.Sprint(path))
	}
	return ""
}

func HealthCheckPort(pn model.PlanNode, fallback int) int {
	if pn.HealthCheck == nil {
		return fallback
	}
	if port, ok := pn.HealthCheck["port"]; ok {
		switch v := port.(type) {
		case float64:
			if v > 0 {
				return int(v)
			}
		case int:
			if v > 0 {
				return v
			}
		case string:
			var n int
			if _, err := fmt.Sscanf(v, "%d", &n); err == nil && n > 0 {
				return n
			}
		}
	}
	return fallback
}
