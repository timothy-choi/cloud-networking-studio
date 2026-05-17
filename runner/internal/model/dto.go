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

type DeploymentResponse struct {
	Status          string  `json:"status"`
	RuntimeProvider string  `json:"runtime_provider"`
	Events          []Event `json:"events"`
	Error           *string `json:"error,omitempty"`
}

type RuntimeStatus struct {
	Status          string `json:"status"`
	RuntimeProvider string `json:"runtime_provider"`
	DockerReachable bool   `json:"docker_reachable"`
	Message         string `json:"message,omitempty"`
}

type DeploymentGetResponse struct {
	DeploymentID    string `json:"deployment_id"`
	TopologyID        string `json:"topology_id"`
	Status            string `json:"status"`
	RuntimeProvider   string `json:"runtime_provider"`
	ContainerIDs      []string `json:"container_ids,omitempty"`
	Error             *string `json:"error,omitempty"`
}

type LogsResponse struct {
	DeploymentID string `json:"deployment_id"`
	NodeID       string `json:"node_id"`
	Logs         string `json:"logs"`
	Error        *string `json:"error,omitempty"`
}

type TrafficRequest struct {
	Type           string `json:"type"` // ping | http
	TopologyID     string `json:"topology_id"`
	SourceNodeID   string `json:"source_node_id"`
	TargetNodeID   string `json:"target_node_id"`
	Count          int    `json:"count,omitempty"`
	Path           string `json:"path,omitempty"`
	Port           int    `json:"port,omitempty"`
	DeploymentID   string `json:"deployment_id,omitempty"`
}

type TrafficResponse struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	Success  bool   `json:"success"`
	Error    *string `json:"error,omitempty"`
}
