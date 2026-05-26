package model

// Infra execution DTOs (Step 57C).

type InfraExecutionRequest struct {
	ExecutionID   string            `json:"execution_id"`
	ExecutionType string            `json:"execution_type"` // terraform | ansible
	Mode          string            `json:"mode"`
	TemplateID    string            `json:"template_id"`
	TemplateDir   string            `json:"template_dir,omitempty"`
	Provider      string            `json:"provider"`
	Variables     map[string]string `json:"variables,omitempty"`
	CredentialsRef string           `json:"credentials_ref,omitempty"`
	CredentialsEnv map[string]string `json:"credentials_env,omitempty"`
	PlanOnly      bool              `json:"plan_only,omitempty"`
	Inventory     map[string]any    `json:"inventory,omitempty"`
	InventoryINI  string            `json:"inventory_ini,omitempty"`
	PlaybookPaths []string          `json:"playbook_paths,omitempty"`
	DeploymentID  string            `json:"deployment_id,omitempty"`
	TopologyID    string            `json:"topology_id,omitempty"`
}

type InfraArtifact struct {
	Type    string `json:"type"`
	URI     string `json:"uri,omitempty"`
	Preview string `json:"preview,omitempty"`
}

type InfraExecutionResponse struct {
	ExecutionID string            `json:"execution_id"`
	Status      string            `json:"status"` // succeeded | failed
	Logs        string            `json:"logs"`
	Artifacts   []InfraArtifact   `json:"artifacts,omitempty"`
	Outputs     map[string]any    `json:"outputs,omitempty"`
	DurationMs  int64             `json:"duration_ms,omitempty"`
	Error       *string           `json:"error,omitempty"`
}
