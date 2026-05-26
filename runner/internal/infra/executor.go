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
	"regexp"
	"strconv"
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

	workdir, cleanup, err := prepareWorkdir(req.ExecutionID, req.TemplateID, req.TemplateDir, req.WorkspaceID, req.PreserveWorkspace)
	if err != nil {
		msg := err.Error()
		resp.Error = &msg
		return resp
	}
	defer cleanup()

	var log strings.Builder
	log.WriteString(fmt.Sprintf("[infra] terraform %s template=%s provider=%s\n", req.Mode, req.TemplateID, req.Provider))
	log.WriteString(fmt.Sprintf("[infra] workdir=%s\n", workdir))
	if req.TemplateDir != "" {
		log.WriteString(fmt.Sprintf("[infra] template_dir=%s\n", req.TemplateDir))
	}
	if req.PlanOnly {
		log.WriteString("[infra] plan_only=true (apply/destroy disabled)\n")
	}
	if req.CredentialsRef != "" {
		log.WriteString(fmt.Sprintf("[infra] credentials_ref=%s\n", req.CredentialsRef))
	}

	if req.PlanOnly && (req.Mode == "apply" || req.Mode == "destroy") {
		msg := "Real cloud apply/destroy is disabled for this provider in plan-only mode."
		resp.Logs = log.String()
		resp.Error = &msg
		return finish(resp, start, req, "failed", msg)
	}

	tfPath, _ := exec.LookPath("terraform")
	useMock := tfPath == "" || req.Provider == "mock" || req.Provider == "local"

	if useMock {
		if tfPath == "" && req.Provider != "mock" && req.Provider != "local" {
			msg := "Terraform CLI is not installed in runner image."
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
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

	if err := writeTerraformTfvars(workdir, req.Variables); err != nil {
		msg := "failed to write terraform.tfvars.json"
		resp.Logs = log.String()
		resp.Error = &msg
		return finish(resp, start, req, "failed", msg)
	}

	cmdEnv := os.Environ()
	for k, v := range req.CredentialsEnv {
		cmdEnv = append(cmdEnv, fmt.Sprintf("%s=%s", k, v))
	}
	if cacheDir := strings.TrimSpace(os.Getenv("TF_PLUGIN_CACHE_DIR")); cacheDir != "" {
		cmdEnv = append(cmdEnv, "TF_PLUGIN_CACHE_DIR="+cacheDir)
	}

	if req.Mode == "fmt" {
		out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "fmt", "-check", "-recursive")
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

	initOut, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "init", "-input=false", "-backend=false")
	log.WriteString(initOut)
	if err != nil {
		msg := "terraform init failed"
		resp.Logs = log.String()
		resp.Error = &msg
		return finish(resp, start, req, "failed", msg)
	}

	switch req.Mode {
	case "validate":
		out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "validate")
		log.WriteString(out)
		if err != nil {
			msg := "terraform validate failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	case "plan":
		planFile := filepath.Join(workdir, "tfplan")
		out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "plan", "-input=false", "-no-color", "-refresh=false", "-out="+planFile)
		log.WriteString(out)
		if err != nil {
			msg := "terraform plan failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
		preview := out
		if len(preview) > 12000 {
			preview = preview[:12000] + "\n... (truncated)"
		}
		resp.Artifacts = append(resp.Artifacts,
			model.InfraArtifact{Type: "plan_file", URI: fmt.Sprintf("workspace://%s/tfplan", req.ExecutionID)},
			model.InfraArtifact{Type: "plan_text", Preview: preview},
		)
	case "apply":
		if req.ApplyFromPlan {
			planFile := filepath.Join(workdir, "tfplan")
			if _, statErr := os.Stat(planFile); statErr != nil {
				msg := "stored terraform plan file missing"
				resp.Logs = log.String()
				resp.Error = &msg
				return finish(resp, start, req, "failed", msg)
			}
			out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "apply", "-input=false", "-no-color", planFile)
			log.WriteString(out)
			if err != nil {
				msg := "terraform apply failed"
				resp.Logs = log.String()
				resp.Error = &msg
				return finish(resp, start, req, "failed", msg)
			}
			resp.Artifacts = append(resp.Artifacts, model.InfraArtifact{Type: "apply_summary", URI: fmt.Sprintf("workspace://%s/apply", req.WorkspaceID)})
		} else {
			out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "apply", "-input=false", "-auto-approve", "-no-color")
			log.WriteString(out)
			if err != nil {
				msg := "terraform apply failed"
				resp.Logs = log.String()
				resp.Error = &msg
				return finish(resp, start, req, "failed", msg)
			}
		}
	case "destroy":
		out, err := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "destroy", "-input=false", "-auto-approve", "-no-color")
		log.WriteString(out)
		if err != nil {
			msg := "terraform destroy failed"
			resp.Logs = log.String()
			resp.Error = &msg
			return finish(resp, start, req, "failed", msg)
		}
	}

	outJSON, _ := runCmdEnv(ctx, workdir, cmdEnv, tfPath, "output", "-json")
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

	workdir, cleanup, err := prepareWorkdir(req.ExecutionID, "", "", "", false)
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
	useMockAnsible := req.Provider == "local" || req.Provider == "mock" || req.Mode == "inventory" || req.Mode == "validate" || ansiblePath == ""
	if useMockAnsible {
		log.WriteString("[infra] mock ansible configure (provider=" + req.Provider + ", mode=" + req.Mode + ")\n")
		resp.Logs = log.String() + fmt.Sprintf("[infra] inventory written to %s\n", inventoryPath)
		if req.Mode == "playbook" {
			log.WriteString("[infra] mock playbooks: install-docker, install-docker-compose, cns-runtime-dirs\n")
			resp.Logs = log.String()
		}
		resp.Outputs["inventory"] = req.Inventory
		resp.Artifacts = []model.InfraArtifact{
			{Type: "configure_summary", URI: "mock://ansible/configure"},
		}
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
		ansibleEnv := append([]string{}, os.Environ()...)
		ansibleEnv = append(ansibleEnv, "ANSIBLE_HOST_KEY_CHECKING=False")
		for k, v := range req.AnsibleEnv {
			ansibleEnv = append(ansibleEnv, fmt.Sprintf("%s=%s", k, v))
		}
		out, err := runCmdEnv(ctx, workdir, ansibleEnv, ansiblePath, "-i", inventoryPath, pbPath)
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

func prepareWorkdir(executionID, templateID, templateDir, workspaceID string, preserve bool) (string, func(), error) {
	var base string
	if strings.TrimSpace(workspaceID) != "" {
		base = filepath.Join(workspacesRoot(), workspaceID)
	} else {
		base = filepath.Join(os.TempDir(), "cns-infra", executionID)
		if err := os.RemoveAll(base); err != nil {
			return "", func() {}, err
		}
	}
	if err := os.MkdirAll(base, 0o700); err != nil {
		return "", func() {}, err
	}
	if templateID != "" {
		mainTf := filepath.Join(base, "main.tf")
		if _, err := os.Stat(mainTf); os.IsNotExist(err) {
			src := resolveTemplateDir(templateID, templateDir)
			if err := copyTemplateDir(src, base); err != nil {
				return "", func() {}, err
			}
		}
	}
	cleanup := func() {}
	if !preserve {
		cleanup = func() { _ = os.RemoveAll(base) }
	}
	return base, cleanup, nil
}

func workspacesRoot() string {
	if v := strings.TrimSpace(os.Getenv("CNS_INFRA_WORKSPACES_ROOT")); v != "" {
		return v
	}
	return "/opt/cns/infra-workspaces"
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

func resolveTemplateDir(templateID, templateDir string) string {
	if strings.TrimSpace(templateDir) != "" {
		return filepath.Join(templatesRoot(), templateDir)
	}
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
	return runCmdEnv(ctx, dir, os.Environ(), bin, args...)
}

func runCmdEnv(ctx context.Context, dir string, env []string, bin string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Dir = dir
	cmd.Env = env
	out, err := cmd.CombinedOutput()
	return string(out), err
}

func writeTerraformTfvars(workdir string, vars map[string]string) error {
	if len(vars) == 0 {
		return nil
	}
	payload := make(map[string]any, len(vars))
	intPattern := regexp.MustCompile(`^-?\d+$`)
	for k, v := range vars {
		if intPattern.MatchString(v) {
			if n, err := strconv.Atoi(v); err == nil {
				payload[k] = n
				continue
			}
		}
		switch strings.ToLower(v) {
		case "true":
			payload[k] = true
		case "false":
			payload[k] = false
		default:
			payload[k] = v
		}
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(workdir, "terraform.tfvars.json"), data, 0o600)
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
