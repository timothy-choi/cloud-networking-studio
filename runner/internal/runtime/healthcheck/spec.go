package healthcheck

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
)

// ProbeSpec is the resolved health-check intent for a workload.
type ProbeSpec struct {
	CheckType       string
	Port            int
	Path            string
	Command         []string
	ExpectedStatus  int
	TimeoutMs       int
	Image           string
	PrimaryPort     int
}

func stringField(m map[string]interface{}, key string) string {
	if m == nil {
		return ""
	}
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(v))
}

func intField(m map[string]interface{}, key string, def int) int {
	if m == nil {
		return def
	}
	v, ok := m[key]
	if !ok || v == nil {
		return def
	}
	switch n := v.(type) {
	case float64:
		return int(n)
	case int:
		return n
	case int64:
		return int(n)
	case string:
		i, err := strconv.Atoi(strings.TrimSpace(n))
		if err == nil {
			return i
		}
	}
	return def
}

func commandField(m map[string]interface{}) []string {
	if m == nil {
		return nil
	}
	v, ok := m["command"]
	if !ok || v == nil {
		return nil
	}
	switch c := v.(type) {
	case string:
		s := strings.TrimSpace(c)
		if s == "" {
			return nil
		}
		return strings.Fields(s)
	case []interface{}:
		out := make([]string, 0, len(c))
		for _, item := range c {
			s := strings.TrimSpace(fmt.Sprint(item))
			if s != "" {
				out = append(out, s)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	case []string:
		return c
	}
	return nil
}

func primaryPortFromNode(pn model.PlanNode) int {
	if len(pn.Ports) > 0 && pn.Ports[0].Port > 0 {
		return pn.Ports[0].Port
	}
	return 0
}

func imageRef(pn model.PlanNode) string {
	if pn.Image == nil {
		return ""
	}
	return strings.TrimSpace(*pn.Image)
}

// ResolveProbeSpec merges explicit health_check config with image/port defaults.
func ResolveProbeSpec(pn model.PlanNode, hc map[string]interface{}) ProbeSpec {
	spec := ProbeSpec{
		CheckType:      "runtime",
		Path:           "/",
		ExpectedStatus: 200,
		TimeoutMs:      8000,
		PrimaryPort:    primaryPortFromNode(pn),
		Image:          imageRef(pn),
	}
	if hc != nil {
		if t := strings.ToLower(stringField(hc, "check_type")); t != "" {
			spec.CheckType = t
		} else if p := stringField(hc, "path"); p != "" {
			spec.CheckType = "http"
			spec.Path = p
		} else if hc["port"] != nil && stringField(hc, "path") == "" && commandField(hc) == nil {
			spec.CheckType = "tcp"
		}
		spec.Port = intField(hc, "port", 0)
		if p := stringField(hc, "path"); p != "" {
			spec.Path = p
		}
		if cmd := commandField(hc); len(cmd) > 0 {
			spec.Command = cmd
			if spec.CheckType == "runtime" {
				spec.CheckType = "command"
			}
		}
		if es := intField(hc, "expected_status", 0); es > 0 {
			spec.ExpectedStatus = es
		}
		if tm := intField(hc, "timeout_ms", 0); tm > 0 {
			spec.TimeoutMs = tm
		}
	}
	if spec.CheckType == "runtime" || spec.CheckType == "" {
		spec.CheckType = inferDefaultCheckType(spec.Image, spec.PrimaryPort)
	}
	if spec.Port <= 0 {
		spec.Port = defaultPortForCheckType(spec.CheckType, spec.PrimaryPort, spec.Image)
	}
	if spec.Path == "" {
		spec.Path = "/"
	}
	if !strings.HasPrefix(spec.Path, "/") {
		spec.Path = "/" + spec.Path
	}
	return spec
}

func inferDefaultCheckType(image string, primaryPort int) string {
	il := strings.ToLower(image)
	switch {
	case strings.Contains(il, "nginx"), strings.Contains(il, "httpd"):
		return "http"
	case strings.Contains(il, "redis"):
		return "tcp"
	case strings.Contains(il, "postgres"):
		return "tcp"
	case primaryPort > 0 && (primaryPort == 80 || primaryPort == 443 || primaryPort == 8080):
		return "http"
	default:
		return "runtime"
	}
}

func defaultPortForCheckType(checkType string, primaryPort int, image string) int {
	il := strings.ToLower(image)
	switch checkType {
	case "http":
		if primaryPort > 0 {
			return primaryPort
		}
		return 80
	case "tcp":
		if primaryPort > 0 && primaryPort != 80 {
			return primaryPort
		}
		if strings.Contains(il, "redis") {
			return 6379
		}
		if strings.Contains(il, "postgres") {
			return 5432
		}
		if primaryPort > 0 {
			return primaryPort
		}
		return 80
	default:
		return primaryPort
	}
}

// ProbeSpecFromRequest builds a probe from API body with legacy port/path fallback.
func ProbeSpecFromRequest(probe model.RuntimeHealthProbeRequest, pn *model.PlanNode) ProbeSpec {
	hc := map[string]interface{}{}
	if strings.TrimSpace(probe.CheckType) != "" {
		hc["check_type"] = probe.CheckType
	}
	if probe.Port > 0 {
		hc["port"] = probe.Port
	}
	if strings.TrimSpace(probe.Path) != "" {
		hc["path"] = probe.Path
	}
	if len(probe.Command) > 0 {
		hc["command"] = probe.Command
	}
	if probe.ExpectedStatus > 0 {
		hc["expected_status"] = probe.ExpectedStatus
	}
	if probe.TimeoutMs > 0 {
		hc["timeout_ms"] = probe.TimeoutMs
	}
	var node model.PlanNode
	if pn != nil {
		node = *pn
	}
	if len(hc) == 0 && pn != nil && pn.HealthCheck != nil {
		return ResolveProbeSpec(*pn, pn.HealthCheck)
	}
	if pn != nil {
		return ResolveProbeSpec(node, hc)
	}
	return ResolveProbeSpec(model.PlanNode{}, hc)
}
