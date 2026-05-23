package healthcheck

import (
	"fmt"
	"strconv"
	"strings"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/trafficutil"
)

type ExecFunc func(argv []string) (stdout, stderr string, exitCode int, err error)

type ContainerStateFunc func() (running bool, status string, err error)

// Run executes a protocol-aware health check inside a workload.
func Run(
	spec ProbeSpec,
	exec ExecFunc,
	state ContainerStateFunc,
) model.RuntimeHealthResponse {
	switch strings.ToLower(strings.TrimSpace(spec.CheckType)) {
	case "none":
		return model.RuntimeHealthResponse{
			Status:  "unsupported",
			Target:  "none",
			Message: "No health check configured.",
		}
	case "runtime":
		return runRuntime(spec, state)
	case "tcp":
		return runTCP(spec, exec)
	case "http":
		return runHTTP(spec, exec)
	case "command":
		return runCommand(spec, exec)
	default:
		return model.RuntimeHealthResponse{
			Status:  "unsupported",
			Target:  spec.CheckType,
			Message: fmt.Sprintf("Unknown check_type %q", spec.CheckType),
		}
	}
}

func runRuntime(spec ProbeSpec, state ContainerStateFunc) model.RuntimeHealthResponse {
	target := "container"
	if spec.Image != "" {
		target = spec.Image
	}
	if state == nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: "runtime state unavailable"}
	}
	running, status, err := state()
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	if running {
		return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: "Container is running (" + status + ")"}
	}
	return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: "Container is not running (" + status + ")"}
}

func runTCP(spec ProbeSpec, exec ExecFunc) model.RuntimeHealthResponse {
	target := fmt.Sprintf("127.0.0.1:%d", spec.Port)
	argv := []string{"sh", "-c", fmt.Sprintf("nc -z -w 3 127.0.0.1 %d", spec.Port)}
	stdout, stderr, code, err := exec(argv)
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	combined := strings.TrimSpace(stderr + "\n" + stdout)
	if code != 0 {
		if trafficutil.NcMissing(combined) || trafficutil.AnyToolMissing(combined, "nc") {
			return unsupportedTool(target, combined)
		}
		// bash /dev/tcp fallback
		argv = []string{"sh", "-c", fmt.Sprintf("(echo >/dev/tcp/127.0.0.1/%d) >/dev/null 2>&1", spec.Port)}
		_, stderr2, code2, err2 := exec(argv)
		if err2 != nil {
			return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err2.Error()}
		}
		if code2 != 0 {
			msg := strings.TrimSpace(stderr2)
			if msg == "" {
				msg = fmt.Sprintf("TCP port %d is not reachable", spec.Port)
			}
			return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: msg}
		}
	}
	return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: "TCP port is reachable"}
}

func runHTTP(spec ProbeSpec, exec ExecFunc) model.RuntimeHealthResponse {
	target := fmt.Sprintf("http://127.0.0.1:%d%s", spec.Port, spec.Path)
	timeoutSec := spec.TimeoutMs / 1000
	if timeoutSec <= 0 {
		timeoutSec = 8
	}
	// wget first, then curl — no installs.
	argv := []string{"wget", "-q", "-S", "-O-", "-T", strconv.Itoa(timeoutSec), target}
	stdout, stderr, code, err := exec(argv)
	combined := strings.TrimSpace(stderr + "\n" + stdout)
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	if code != 0 && trafficutil.HTTPWgetMissing(combined) {
		argv = []string{"curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", strconv.Itoa(timeoutSec), target}
		stdout, stderr, code, err = exec(argv)
		combined = strings.TrimSpace(stderr + "\n" + stdout)
		if code != 0 && (trafficutil.HTTPCurlMissing(combined) || trafficutil.HTTPWgetMissing(combined)) {
			return unsupportedTool(target, combined)
		}
		if code == 0 {
			statusCode, _ := strconv.Atoi(strings.TrimSpace(stdout))
			if statusCode >= spec.ExpectedStatus && statusCode < 500 {
				return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: fmt.Sprintf("HTTP %d", statusCode)}
			}
			return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: fmt.Sprintf("HTTP status %d", statusCode)}
		}
		if trafficutil.HTTPConnectionRefused(combined) {
			return model.RuntimeHealthResponse{
				Status:  "failed",
				Target:  target,
				Message: trafficutil.NoHTTPServiceMessage,
			}
		}
	}
	if code != 0 {
		if trafficutil.HTTPWgetMissing(combined) || trafficutil.HTTPCurlMissing(combined) {
			return unsupportedTool(target, combined)
		}
		if trafficutil.HTTPConnectionRefused(combined) {
			return model.RuntimeHealthResponse{
				Status:  "failed",
				Target:  target,
				Message: trafficutil.NoHTTPServiceMessage,
			}
		}
		msg := combined
		if msg == "" {
			msg = fmt.Sprintf("HTTP check failed with exit %d", code)
		}
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: msg}
	}
	return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: "HTTP check succeeded inside container"}
}

func runCommand(spec ProbeSpec, exec ExecFunc) model.RuntimeHealthResponse {
	if len(spec.Command) == 0 {
		return model.RuntimeHealthResponse{Status: "unsupported", Target: "command", Message: "No command configured for command health check."}
	}
	target := strings.Join(spec.Command, " ")
	stdout, stderr, code, err := exec(spec.Command)
	combined := strings.TrimSpace(stderr + "\n" + stdout)
	if err != nil {
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: err.Error()}
	}
	if code != 0 {
		if trafficutil.AnyToolMissing(combined, spec.Command[0]) {
			return unsupportedTool(target, combined)
		}
		msg := combined
		if msg == "" {
			msg = fmt.Sprintf("command exited %d", code)
		}
		return model.RuntimeHealthResponse{Status: "failed", Target: target, Message: msg}
	}
	out := strings.TrimSpace(stdout)
	if out == "" {
		out = "command succeeded"
	}
	return model.RuntimeHealthResponse{Status: "passed", Target: target, Message: out}
}

func unsupportedTool(target, detail string) model.RuntimeHealthResponse {
	msg := trafficutil.ToolUnavailableMessage
	if detail != "" {
		msg = msg + " (" + detail + ")"
	}
	return model.RuntimeHealthResponse{Status: "unsupported", Target: target, Message: msg}
}
