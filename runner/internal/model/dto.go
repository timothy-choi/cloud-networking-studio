package model

// JSON DTOs shared with the FastAPI control plane.

type PlanNode struct {
	ID         string  `json:"id"`
	Name       string  `json:"name"`
	Image      *string `json:"image"`
	IPAddress  *string `json:"ip_address"`
	NodeType   string  `json:"node_type"`
}

type PlanLink struct {
	LinkID        string  `json:"link_id"`
	SourceNodeID  string  `json:"source_node_id"`
	TargetNodeID  string  `json:"target_node_id"`
	NetworkName   string  `json:"network_name"`
	CIDR          *string `json:"cidr"`
	SourceIP      *string `json:"source_ip"`
	TargetIP      *string `json:"target_ip"`
}

type DeploymentRequest struct {
	DeploymentID        string     `json:"deployment_id"`
	ProjectID           *string    `json:"project_id"`
	TopologyID          string     `json:"topology_id"`
	RequestedByUserID   *string    `json:"requested_by_user_id"`
	RuntimeTarget       string     `json:"runtime_target"`
	NetworkingMode      string     `json:"networking_mode"`
	SegmentedNetworks   bool       `json:"segmented_networks"`
	SubnetCIDR          *string    `json:"subnet_cidr"`
	Nodes               []PlanNode `json:"nodes"`
	PlanLinks           []PlanLink `json:"plan_links"`
	Metadata            any        `json:"metadata,omitempty"`
}

type Event struct {
	Level   string `json:"level"`
	Message string `json:"message"`
}

// RuntimePort describes a listener on a workload or service.
type RuntimePort struct {
	Port       int    `json:"port"`
	TargetPort int    `json:"target_port,omitempty"`
	Protocol   string `json:"protocol"`
}

// RuntimeAccessResource is one materialized unit (node, service, network, …).
type RuntimeAccessResource struct {
	Type                 string            `json:"type"`
	NodeID               string            `json:"node_id,omitempty"`
	ServiceID            string            `json:"service_id,omitempty"`
	Name                 string            `json:"name"`
	RuntimeName          string            `json:"runtime_name"`
	Status               string            `json:"status,omitempty"`
	NamespaceOrNetwork   string            `json:"namespace_or_network,omitempty"`
	Ports                []RuntimePort     `json:"ports,omitempty"`
	InternalURL          string            `json:"internal_url,omitempty"`
	ExternalURL          *string           `json:"external_url,omitempty"`
	Metadata             map[string]string `json:"metadata,omitempty"`
}

// RuntimeAccess is returned on successful deploy for control-plane persistence and UX.
type RuntimeAccess struct {
	DeploymentID       string                  `json:"deployment_id"`
	TopologyID         string                  `json:"topology_id"`
	Status             string                  `json:"status"`
	RuntimeProvider    string                  `json:"runtime_provider"`
	NamespaceOrNetwork string                  `json:"namespace_or_network"`
	Resources          []RuntimeAccessResource `json:"resources"`
}

type DeploymentResponse struct {
	Status          string         `json:"status"`
	RuntimeProvider string         `json:"runtime_provider"`
	Events          []Event        `json:"events"`
	RuntimeAccess   *RuntimeAccess `json:"runtime_access,omitempty"`
	Error           *string        `json:"error,omitempty"`
}

type RuntimeStatus struct {
	Status                 string `json:"status"`
	RuntimeProvider        string `json:"runtime_provider"`
	DockerReachable        bool   `json:"docker_reachable"`
	KubernetesReachable    bool   `json:"kubernetes_reachable"`
	CurrentContext         string `json:"current_context,omitempty"`
	Message                string `json:"message,omitempty"`
}

type ResourceRef struct {
	Kind      string `json:"kind"`
	Name      string `json:"name"`
	Namespace string `json:"namespace"`
}

type DeploymentGetResponse struct {
	DeploymentID    string         `json:"deployment_id"`
	TopologyID      string         `json:"topology_id"`
	Status          string         `json:"status"`
	RuntimeProvider string         `json:"runtime_provider"`
	ContainerIDs    []string       `json:"container_ids,omitempty"`
	Namespace       string         `json:"namespace,omitempty"`
	Resources       []ResourceRef  `json:"resources,omitempty"`
	Error           *string        `json:"error,omitempty"`
}

type LogsResponse struct {
	DeploymentID string `json:"deployment_id"`
	NodeID       string `json:"node_id"`
	Logs         string `json:"logs"`
	Error        *string `json:"error,omitempty"`
}

type TrafficRequest struct {
	Type           string  `json:"type"` // ping | http
	TopologyID     string  `json:"topology_id"`
	SourceNodeID   string  `json:"source_node_id"`
	TargetNodeID   string  `json:"target_node_id"`
	Count          int     `json:"count,omitempty"`
	Path           string  `json:"path,omitempty"`
	Port           int     `json:"port,omitempty"`
	DeploymentID   string  `json:"deployment_id,omitempty"`
	ProjectID      *string `json:"project_id,omitempty"`
}

type TrafficResponse struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	Success  bool   `json:"success"`
	Error    *string `json:"error,omitempty"`
}

// RuntimeLogsItem is one workload slice inside a deployment-wide log bundle.
type RuntimeLogsItem struct {
	ServiceID string `json:"service_id,omitempty"`
	NodeID    string `json:"node_id,omitempty"`
	Name      string `json:"name,omitempty"`
	Logs      string `json:"logs,omitempty"`
	Error     string `json:"error,omitempty"`
}

// RuntimeDeploymentLogsResponse is returned by GET .../runtime/logs and per-service log routes.
type RuntimeDeploymentLogsResponse struct {
	DeploymentID    string            `json:"deployment_id"`
	ServiceID       string            `json:"service_id,omitempty"`
	Logs            string            `json:"logs"`
	Items           []RuntimeLogsItem `json:"items"`
	RuntimeProvider string            `json:"runtime_provider"`
}

// RuntimeHealthProbeRequest optional POST body for health-check.
type RuntimeHealthProbeRequest struct {
	Port int    `json:"port,omitempty"`
	Path string `json:"path,omitempty"`
}

// RuntimeHealthResponse is returned by POST .../health-check.
type RuntimeHealthResponse struct {
	Status    string `json:"status"` // passed | failed | unsupported
	Target    string `json:"target"`
	LatencyMs *int64 `json:"latency_ms,omitempty"`
	Message   string `json:"message"`
}

// RuntimeTrafficOpRequest is the body for POST .../runtime/traffic-tests.
type RuntimeTrafficOpRequest struct {
	TopologyID     string  `json:"topology_id,omitempty"`
	DeploymentID   string  `json:"deployment_id,omitempty"`
	ProjectID      *string `json:"project_id,omitempty"`
	SourceNodeID   string  `json:"source_node_id"`
	Target         string  `json:"target"` // topology node id or http(s):// URL
	Protocol       string  `json:"protocol"` // http | ping
	Path           string  `json:"path,omitempty"`
	Port           int     `json:"port,omitempty"`
	Count          int     `json:"count,omitempty"`
}

// RuntimeTrafficOpResponse is returned by POST .../runtime/traffic-tests.
type RuntimeTrafficOpResponse struct {
	Status    string `json:"status"` // passed | failed | unsupported
	Source    string `json:"source"`
	Target    string `json:"target"`
	Protocol  string `json:"protocol"`
	Output    string `json:"output"`
	LatencyMs *int64 `json:"latency_ms,omitempty"`
}

// RuntimeExecRequest is the body for POST .../runtime/services/{id}/exec.
type RuntimeExecRequest struct {
	Command         string `json:"command"`
	TimeoutSeconds int    `json:"timeout_seconds"`
}

// RuntimeExecResponse is returned by the runner exec endpoint (no DB id).
type RuntimeExecResponse struct {
	DeploymentID    string `json:"deployment_id"`
	ServiceID       string `json:"service_id"`
	Command         string `json:"command"`
	Status          string `json:"status"` // succeeded | failed | timeout | unsupported | rejected
	ExitCode        *int   `json:"exit_code,omitempty"`
	Stdout          string `json:"stdout"`
	Stderr          string `json:"stderr"`
	StartedAt       string `json:"started_at"`
	FinishedAt      string `json:"finished_at"`
	RuntimeProvider string `json:"runtime_provider"`
	Message         string `json:"message,omitempty"`
}

// RuntimeRestartResponse is returned by POST .../restart.
type RuntimeRestartResponse struct {
	Status          string `json:"status"` // accepted | succeeded | failed | unsupported
	Message         string `json:"message"`
	RuntimeProvider string `json:"runtime_provider"`
}
