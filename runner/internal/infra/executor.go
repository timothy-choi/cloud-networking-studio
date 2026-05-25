// Package infra executes whitelisted Terraform and Ansible jobs (Step 57C).
package infra

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/observability"
)

var allowedTemplates = map[string]bool{
	"local-mock": true,
	"gcp-vm":     true,
	"aws-ec2":    true,
	"docker-vm":  true,
}

var allowedTerraformModes = map[string]bool{
	"validate": true,
	"fmt":      true,
	"plan":     true,
	"apply":    true,
	"destroy":  true,
}

var allowedAnsibleModes = map[string]bool{
	"validate":  true,
	"inventory": true,
	"playbook":  true,
}

// Execute runs one infrastructure job in an isolated temp directory.
func Execute(ctx context.Context, req model.InfraExecutionRequest) model.InfraExecutionResponse {
	start := time.Now()
	resp := model.InfraExecutionResponse{
		ExecutionID: req.ExecutionID,
		Status:      "failed",
		Logs:        "",
		Artifacts:   []model.InfraArtifact{},
		Outputs:     map[string]any{},
	}

	if req.ExecutionID == "" {
		msg := "execution_id is required"
		resp.Error = &msg
		return resp
	}
	if !allowedTemplates[req.TemplateID] {
		msg := fmt.Sprintf("template_id %q is not allowlisted", req.TemplateID)
		resp.Error = &msg
		return resp
	}

	switch req.ExecutionType {
	case "terraform":
		return executeTerraform(ctx, req, start)
	case "ansible":
		return executeAnsible(ctx, req, start)
	default:
		msg := fmt.Sprintf("unsupported execution_type %q", req.ExecutionType)
		resp.Error = &msg
		return resp
	}
}

func executeTerraform(ctx context.Context, req model.InfraExecutionRequest, start time.Time) model.InfraExecutionResponse {
	resp := model.InfraExecutionResponse{
		ExecutionID: req.ExecutionID,
		Status:      "failed",
		Outputs:     map[string]any{},
	}
	if !allowedTerraformModes[req.Mode] {
		msg := fmt.Sprintf("unsupported terraform mode %q", req.Mode)
		resp.Error = &msg
		return resp
	}

	workdir, cleanup, err := prepareWorkdir(req.ExecutionID, req.TemplateID)
	if err != nil {
		msg := err.Error()
		resp.Error = &msg
		return resp
	}
	defer cleanup()

	var log strings.Builder
	log.WriteString(fmt.Sprintf("[infra] terraform %s template=%s provider=%s\n", req.Mode, req.TemplateID, req.Provider))
	log.WriteString(fmt.Sprintf("[infra] workdir=%s\n", workdir))

	tfPath, _ := exec.LookPath("terraform")
	useMock := tfPath == "" || req.Provider == "mock" || req.Provider == "local"

	if useMock {
		log.WriteString("[infra] terraform binary unavailable or local/mock provider — using mock executor\n")
		outputs := mockTerraformOutputs(req)
		resp.Outputs = outputs
		resp.Logs = log.String() + mockTerraformLogs(req.Mode, outputs)
		resp.Status = "succeeded"
		resp.Artifacts = []model.InfraArtifact{
			{Type: "plan_file", URI: fmt.Sprintf("workspace://%s/plan.out", req.ExecutionID)},
		}
		resp.DurationMs = time.Since(start).Milliseconds()
		observability.RecordOperation(observability.OperationRecord{
			Operation:    "infra_terraform_" + req.Mode,
			Provider:     "infra",
			Status:       "succeeded",
			DurationMs:   resp.DurationMs,
			DeploymentID: req.DeploymentID,
			TopologyID:   req.TopologyID,
		})
		return resp
	}

	if req.Mode == "fmt" {
		out, err := runCmd(ctx, workdir, tfPath, "fmt", "-check", "-recursive")
		log.WriteString(out)
		if err != nil {
			msg := "terraform fmt check failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
		resp.Logs = log.String()
		resp.Status = "succeeded"
		return finish(resp, start, req, "succeeded", "")
	}

	initOut, err := runCmd(ctx, workdir, tfPath, "init", "-input=false", "-backend=false")
	log.WriteString(initOut)
	if err != nil {
		msg := "terraform init failed"
		resp.Logs = log.String()
		resp.Error = &msg
		return finish(resp, start, req, "failed", msg)
	}

	varArgs := terraformVarArgs(req.Variables)
	switch req.Mode {
	case "validate":
		out, err := runCmd(ctx, workdir, tfPath, append([]string{"validate"}, varArgs...)...)
		log.WriteString(out)
		if err != nil {
			msg := "terraform validate failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	case "plan":
		out, err := runCmd(ctx, workdir, tfPath, append([]string{"plan", "-input=false", "-no-color"}, varArgs...)...)
		log.WriteString(out)
		if err != nil {
			msg := "terraform plan failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
		resp.Artifacts = append(resp.Artifacts, model.InfraArtifact{Type: "plan_file", URI: fmt.Sprintf("workspace://%s/plan.out", req.ExecutionID)})
	case "apply":
		out, err := runCmd(ctx, workdir, tfPath, append([]string{"apply", "-input=false", "-auto-approve", "-no-color"}, varArgs...)...)
		log.WriteString(out)
		if err != nil {
			msg := "terraform apply failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	case "destroy":
		out, err := runCmd(ctx, workdir, tfPath, append([]string{"destroy", "-input=false", "-auto-approve", "-no-color"}, varArgs...)...)
		log.WriteString(out)
		if err != nil {
			msg := "terraform destroy failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	}

	outJSON, _ := runCmd(ctx, workdir, tfPath, "output", "-json")
	if strings.TrimSpace(outJSON) != "" {
		var parsed map[string]any
		if json.Unmarshal([]byte(outJSON), &parsed) == nil {
			for k, v := range unwrapTerraformOutputs(parsed) {
				resp.Outputs[k] = v
			}
		}
	}
	if len(resp.Outputs) == 0 {
		resp.Outputs = mockTerraformOutputs(req)
	}

	resp.Logs = log.String()
	resp.Status = "succeeded"
	return finish(resp, start, req, "succeeded", "")
}

func executeAnsible(ctx context.Context, req model.InfraExecutionRequest, start time.Time) model.InfraExecutionResponse {
	resp := model.InfraExecutionResponse{
		ExecutionID: req.ExecutionID,
		Status:      "failed",
		Outputs:     map[string]any{},
	}
	if !allowedAnsibleModes[req.Mode] {
		msg := fmt.Sprintf("unsupported ansible mode %q", req.Mode)
		resp.Error = &msg
		return resp
	}

	workdir, cleanup, err := prepareWorkdir(req.ExecutionID, "")
	if err != nil {
		msg := err.Error()
		resp.Error = &msg
		return resp
	}
	defer cleanup()

	var log strings.Builder
	log.WriteString(fmt.Sprintf("[infra] ansible %s template=%s\n", req.Mode, req.TemplateID))

	inventoryPath := filepath.Join(workdir, "inventory.ini")
	if err := os.WriteFile(inventoryPath, []byte(req.InventoryINI), 0o600); err != nil {
		msg := "failed to write inventory"
		resp.Error = &msg
		return resp
	}

	ansiblePath, _ := exec.LookPath("ansible-playbook")
	if ansiblePath == "" || req.Mode == "inventory" {
		log.WriteString("[infra] ansible-playbook unavailable or inventory mode — mock configure\n")
		resp.Logs = log.String() + fmt.Sprintf("[infra] inventory written to %s\n", inventoryPath)
		resp.Outputs["inventory"] = req.Inventory
		resp.Status = "succeeded"
		return finish(resp, start, req, "succeeded", "")
	}

	for _, pb := range req.PlaybookPaths {
		pbPath := resolvePlaybookPath(pb)
		if !isAllowedPlaybook(pbPath) {
			msg := fmt.Sprintf("playbook not allowlisted: %s", pb)
			resp.Error = &msg
			return resp
		}
		out, err := runCmd(ctx, workdir, ansiblePath, "-i", inventoryPath, pbPath)
		log.WriteString(fmt.Sprintf("[infra] playbook %s\n%s\n", filepath.Base(pbPath), out))
		if err != nil {
			msg := fmt.Sprintf("ansible-playbook failed: %s", filepath.Base(pbPath))
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	}

	resp.Logs = log.String()
	resp.Outputs["inventory"] = req.Inventory
	resp.Status = "succeeded"
	return finish(resp, start, req, "succeeded", "")
}

func prepareWorkdir(executionID, templateID string) (string, func(), error) {
	base := filepath.Join(os.TempDir(), "cns-infra", executionID)
	if err := os.RemoveAll(base); err != nil {
		return "", func() {}, err
	}
	if err := os.MkdirAll(base, 0o700); err != nil {
		return "", func() {}, err
	}
	if templateID != "" {
		src := resolveTemplateDir(templateID)
		if err := copyTemplateDir(src, base); err != nil {
			return "", func() {}, err
		}
	}
	return base, func() { _ = os.RemoveAll(base) }, nil
}

func templatesRoot() string {
	if v := strings.TrimSpace(os.Getenv("CNS_INFRA_TEMPLATES_ROOT")); v != "" {
		return v
	}
	return "/opt/cns/infra_templates"
}

func playbooksRoot() string {
	if v := strings.TrimSpace(os.Getenv("CNS_ANSIBLE_PLAYBOOKS_ROOT")); v != "" {
		return v
	}
	return "/opt/cns/ansible_playbooks"
}

func resolveTemplateDir(templateID string) string {
	return filepath.Join(templatesRoot(), templateID)
}

func resolvePlaybookPath(nameOrPath string) string {
	base := filepath.Base(nameOrPath)
	return filepath.Join(playbooksRoot(), base)
}

func copyTemplateDir(src, dst string) error {
	info, err := os.Stat(src)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		return fmt.Errorf("template dir is not a directory")
	}
	return filepath.Walk(src, func(path string, fi os.FileInfo, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if fi.IsDir() {
			return os.MkdirAll(target, 0o700)
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
		if err != nil {
			return err
		}
		_, cpErr := io.Copy(out, in)
		closeErr := out.Close()
		if cpErr != nil {
			return cpErr
		}
		return closeErr
	})
}

func runCmd(ctx context.Context, dir, bin string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Dir = dir
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func terraformVarArgs(vars map[string]string) []string {
	args := make([]string, 0, len(vars)*2)
	for k, v := range vars {
		args = append(args, "-var", fmt.Sprintf("%s=%s", k, v))
	}
	return args
}

func mockTerraformOutputs(req model.InfraExecutionRequest) map[string]any {
	name := req.Variables["deployment_name"]
	if name == "" {
		name = "cns-infra"
	}
	count := 1
	hosts := []map[string]any{
		{
			"name":       fmt.Sprintf("%s-vm-1", name),
			"public_ip":  "203.0.113.10",
			"private_ip": "10.0.0.10",
			"ssh_user":   "ubuntu",
			"ssh_port":   22,
		},
	}
	return map[string]any{
		"vm_count":      count,
		"region":        req.Variables["region"],
		"hosts":         hosts,
		"exposed_ports": []int{22, 80, 443},
	}
}

func mockTerraformLogs(mode string, outputs map[string]any) string {
	b, _ := json.MarshalIndent(outputs, "", "  ")
	return fmt.Sprintf("[infra] mock terraform %s completed\noutputs:\n%s\n", mode, string(b))
}

func unwrapTerraformOutputs(parsed map[string]any) map[string]any {
	out := map[string]any{}
	for k, wrapper := range parsed {
		m, ok := wrapper.(map[string]any)
		if !ok {
			continue
		}
		if v, ok := m["value"]; ok {
			out[k] = v
		}
	}
	return out
}

func isAllowedPlaybook(path string) bool {
	base := filepath.Base(path)
	allowed := map[string]bool{
		"install-docker.yml":                true,
		"install-docker-compose.yml":        true,
		"cns-runtime-dirs.yml":              true,
		"monitoring-agent-placeholder.yml":  true,
		"firewall-placeholder.yml":          true,
	}
	return allowed[base]
}

func finish(resp model.InfraExecutionResponse, start time.Time, req model.InfraExecutionRequest, status, errMsg string) model.InfraExecutionResponse {
	resp.Status = status
	resp.DurationMs = time.Since(start).Milliseconds()
	observability.RecordOperation(observability.OperationRecord{
		Operation:    "infra_" + req.ExecutionType + "_" + req.Mode,
		Provider:     "infra",
		Status:       status,
		DurationMs:   resp.DurationMs,
		DeploymentID: req.DeploymentID,
		TopologyID:   req.TopologyID,
		ErrorMessage: errMsg,
	})
	if errMsg != "" {
		resp.Error = &errMsg
	}
	return resp
}
