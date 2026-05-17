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
