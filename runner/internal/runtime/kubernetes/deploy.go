package kubernetes

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/client-go/kubernetes"

	"github.com/timothy-choi/cloud-networking-studio/runner/internal/model"
	"github.com/timothy-choi/cloud-networking-studio/runner/internal/runtime/nodeconfig"
)

const cnsContainerName = "node"

func derefStr(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}

func baseLabels(req *model.DeploymentRequest) map[string]string {
	pid := derefStr(req.ProjectID)
	l := map[string]string{
		"app":                     "cloud-networking-studio",
		"topology_id":             strings.TrimSpace(req.TopologyID),
		"deployment_id":           strings.TrimSpace(req.DeploymentID),
		"cns.io/managed-by":       "cns-runner",
		"cns.io/runtime-provider": "kubernetes",
	}
	if pid != "" {
		l["project_id"] = pid
	}
	return l
}

func defaultResourceRequirements() corev1.ResourceRequirements {
	return corev1.ResourceRequirements{
		Requests: corev1.ResourceList{
			corev1.ResourceCPU:    resource.MustParse("50m"),
			corev1.ResourceMemory: resource.MustParse("64Mi"),
		},
		Limits: corev1.ResourceList{
			corev1.ResourceCPU:    resource.MustParse("500m"),
			corev1.ResourceMemory: resource.MustParse("512Mi"),
		},
	}
}

func serviceTypeForNode(pn model.PlanNode) corev1.ServiceType {
	if pn.KubernetesServiceType != nil {
		switch strings.ToLower(strings.TrimSpace(*pn.KubernetesServiceType)) {
		case "nodeport", "node_port":
			return corev1.ServiceTypeNodePort
		}
	}
	return corev1.ServiceTypeClusterIP
}

func lookupPodIP(ctx context.Context, client kubernetes.Interface, ns, nodeID string) string {
	sel := "cns.io/node-id=" + strings.TrimSpace(nodeID)
	pods, err := client.CoreV1().Pods(ns).List(ctx, metav1.ListOptions{LabelSelector: sel})
	if err != nil {
		return ""
	}
	for _, p := range pods.Items {
		if strings.TrimSpace(p.Status.PodIP) != "" {
			return p.Status.PodIP
		}
	}
	return ""
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

func deploymentNameForNode(pn model.PlanNode) string {
	safe := dnsLabel.ReplaceAllString(strings.ToLower(strings.TrimSpace(pn.Name)), "-")
	safe = strings.Trim(safe, "-")
	if safe == "" {
		safe = "node"
	}
	if len(safe) > 40 {
		safe = safe[:40]
	}
	return sanitizeRFC1123Label("cns-node-" + safe + "-" + short8(pn.ID))
}

// Deploy creates namespace, ConfigMap, Deployments, and ClusterIP Services for a topology.
func Deploy(ctx context.Context, client kubernetes.Interface, req *model.DeploymentRequest) model.DeploymentResponse {
	ev := func(level, msg string) model.Event { return model.Event{Level: level, Message: msg} }
	var events []model.Event
	if req.SegmentedNetworks {
		msg := "segmented multinet topologies are not supported by the Kubernetes runner yet"
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: []model.Event{ev("error", msg)}, Error: &msg}
	}
	if strings.TrimSpace(req.TopologyID) == "" || strings.TrimSpace(req.DeploymentID) == "" {
		msg := "topology_id and deployment_id are required"
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: []model.Event{ev("error", msg)}, Error: &msg}
	}
	if len(req.Nodes) == 0 {
		msg := "at least one node is required"
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: []model.Event{ev("error", msg)}, Error: &msg}
	}

	ns := NamespaceFor(derefStr(req.ProjectID), req.TopologyID, req.DeploymentID)
	events = append(events, ev("info", fmt.Sprintf("Kubernetes: using namespace %s", ns)))

	var accessResources []model.RuntimeAccessResource
	accessResources = append(accessResources, model.RuntimeAccessResource{
		Type:               "namespace",
		Name:               ns,
		RuntimeName:        ns,
		Status:             "active",
		NamespaceOrNetwork: ns,
		Metadata:           map[string]string{"topology_id": strings.TrimSpace(req.TopologyID)},
	})

	_, err := client.CoreV1().Namespaces().Get(ctx, ns, metav1.GetOptions{})
	if apierrors.IsNotFound(err) {
		_, err = client.CoreV1().Namespaces().Create(ctx, &corev1.Namespace{
			ObjectMeta: metav1.ObjectMeta{
				Name:   ns,
				Labels: baseLabels(req),
			},
		}, metav1.CreateOptions{})
		if err != nil {
			msg := fmt.Sprintf("namespace create failed: %v", err)
			events = append(events, ev("error", msg))
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: events, Error: &msg}
		}
		events = append(events, ev("info", "Kubernetes namespace created"))
	} else if err != nil {
		msg := fmt.Sprintf("namespace lookup failed: %v", err)
		events = append(events, ev("error", msg))
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: events, Error: &msg}
	} else {
		events = append(events, ev("info", "Kubernetes namespace already exists"))
	}

	metaJSON, _ := json.Marshal(req)
	cm := &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "cns-topology-metadata",
			Namespace: ns,
			Labels:    baseLabels(req),
		},
		Data: map[string]string{"deployment.json": string(metaJSON)},
	}
	if _, err := client.CoreV1().ConfigMaps(ns).Get(ctx, cm.Name, metav1.GetOptions{}); apierrors.IsNotFound(err) {
		_, err = client.CoreV1().ConfigMaps(ns).Create(ctx, cm, metav1.CreateOptions{})
	} else if err == nil {
		_, err = client.CoreV1().ConfigMaps(ns).Update(ctx, cm, metav1.UpdateOptions{})
	}
	if err != nil {
		msg := fmt.Sprintf("configmap failed: %v", err)
		events = append(events, ev("error", msg))
		_ = DestroyNamespace(ctx, client, ns)
		return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: events, Error: &msg}
	}
	events = append(events, ev("info", "Kubernetes ConfigMap applied"))

	for _, pn := range req.Nodes {
		dname := deploymentNameForNode(pn)
		img := resolveImage(pn.Image)
		cmd := nodeconfig.ResolveContainerCommand(pn, img)
		ports := nodeconfig.EffectivePorts(pn)
		portNum := nodeconfig.PrimaryPort(pn)
		role := nodeconfig.ResolveForwardingRole(pn)
		podLabels := map[string]string{
			"app":                     "cloud-networking-studio",
			"topology_id":             strings.TrimSpace(req.TopologyID),
			"deployment_id":           strings.TrimSpace(req.DeploymentID),
			"cns.io/node-id":          strings.TrimSpace(pn.ID),
			"cns.io/managed-by":       "cns-runner",
			"cns.io/runtime-provider": "kubernetes",
			"cns.io/forwarding-role":  role,
		}
		if pid := derefStr(req.ProjectID); pid != "" {
			podLabels["project_id"] = pid
		}

		var cmdSlice []string
		if cmd != nil {
			cmdSlice = append(cmdSlice, cmd...)
		}
		var containerPorts []corev1.ContainerPort
		for i, p := range ports {
			name := "p"
			if i == 0 {
				name = "http"
			} else {
				name = fmt.Sprintf("p%d", p.Port)
			}
			containerPorts = append(containerPorts, corev1.ContainerPort{
				ContainerPort: int32(p.TargetPort),
				Name:          name,
				Protocol:      corev1.ProtocolTCP,
			})
		}
		if len(containerPorts) == 0 {
			containerPorts = []corev1.ContainerPort{{ContainerPort: 80, Name: "http", Protocol: corev1.ProtocolTCP}}
		}
		var envVars []corev1.EnvVar
		for k, v := range pn.Env {
			k = strings.TrimSpace(k)
			if k == "" {
				continue
			}
			envVars = append(envVars, corev1.EnvVar{Name: k, Value: v})
		}
		container := corev1.Container{
			Name:      cnsContainerName,
			Image:     img,
			Command:   cmdSlice,
			Ports:     containerPorts,
			Env:       envVars,
			Resources: defaultResourceRequirements(),
		}
		if hcPath := nodeconfig.HealthCheckPath(pn); hcPath != "" {
			hcPort := int32(nodeconfig.HealthCheckPort(pn, portNum))
			container.LivenessProbe = &corev1.Probe{
				ProbeHandler: corev1.ProbeHandler{
					HTTPGet: &corev1.HTTPGetAction{
						Path: hcPath,
						Port: intstr.FromInt(int(hcPort)),
					},
				},
			}
		}
		dep := &appsv1.Deployment{
			ObjectMeta: metav1.ObjectMeta{
				Name:      dname,
				Namespace: ns,
				Labels:    podLabels,
			},
			Spec: appsv1.DeploymentSpec{
				Replicas: int32Ptr(1),
				Selector: &metav1.LabelSelector{MatchLabels: map[string]string{"cns.io/node-id": strings.TrimSpace(pn.ID)}},
				Template: corev1.PodTemplateSpec{
					ObjectMeta: metav1.ObjectMeta{Labels: podLabels},
					Spec: corev1.PodSpec{
						Containers: []corev1.Container{container},
					},
				},
			},
		}
		if _, err := client.AppsV1().Deployments(ns).Get(ctx, dname, metav1.GetOptions{}); apierrors.IsNotFound(err) {
			_, err = client.AppsV1().Deployments(ns).Create(ctx, dep, metav1.CreateOptions{})
		} else if err == nil {
			_, err = client.AppsV1().Deployments(ns).Update(ctx, dep, metav1.UpdateOptions{})
		}
		if err != nil {
			msg := fmt.Sprintf("deployment %s failed: %v", dname, err)
			events = append(events, ev("error", msg))
			_ = DestroyNamespace(ctx, client, ns)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: events, Error: &msg}
		}
		events = append(events, ev("info", fmt.Sprintf("Kubernetes Deployment applied: %s/%s", ns, dname)))

		svcName := dname + "-svc"
		var svcPorts []corev1.ServicePort
		for i, p := range ports {
			name := "http"
			if i > 0 {
				name = fmt.Sprintf("p%d", p.Port)
			}
			svcPorts = append(svcPorts, corev1.ServicePort{
				Name:       name,
				Port:       int32(p.Port),
				TargetPort: intstr.FromInt(p.TargetPort),
				Protocol:   corev1.ProtocolTCP,
			})
		}
		if len(svcPorts) == 0 {
			svcPorts = []corev1.ServicePort{{
				Name:       "http",
				Port:       80,
				TargetPort: intstr.FromInt(80),
				Protocol:   corev1.ProtocolTCP,
			}}
		}
		svcType := serviceTypeForNode(pn)
		svc := &corev1.Service{
			ObjectMeta: metav1.ObjectMeta{
				Name:      svcName,
				Namespace: ns,
				Labels:    podLabels,
			},
			Spec: corev1.ServiceSpec{
				Selector: map[string]string{"cns.io/node-id": strings.TrimSpace(pn.ID)},
				Ports:    svcPorts,
				Type:     svcType,
			},
		}
		if _, err := client.CoreV1().Services(ns).Get(ctx, svcName, metav1.GetOptions{}); apierrors.IsNotFound(err) {
			_, err = client.CoreV1().Services(ns).Create(ctx, svc, metav1.CreateOptions{})
		} else if err == nil {
			_, err = client.CoreV1().Services(ns).Update(ctx, svc, metav1.UpdateOptions{})
		}
		if err != nil {
			msg := fmt.Sprintf("service %s failed: %v", svcName, err)
			events = append(events, ev("error", msg))
			_ = DestroyNamespace(ctx, client, ns)
			return model.DeploymentResponse{Status: "failed", RuntimeProvider: "kubernetes", Events: events, Error: &msg}
		}
		events = append(events, ev("info", fmt.Sprintf("Kubernetes Service applied: %s/%s", ns, svcName)))

		internalURL := clusterInternalServiceURL(ns, svcName, portNum)
		nid := strings.TrimSpace(pn.ID)
		metaBase := nodeconfig.PlanNodeRuntimeMeta(pn, img, cmd)
		metaBase["deployment"] = dname
		metaBase["service"] = svcName
		metaBase["cluster_service_type"] = string(svcType)
		if svcType == corev1.ServiceTypeNodePort {
			metaBase["public_access"] = "nodeport"
			metaBase["exposure_mode"] = "nodeport"
		} else {
			metaBase["public_access"] = "internal_only"
			metaBase["exposure_mode"] = "clusterip"
			metaBase["manual_port_forward_cmd"] = fmt.Sprintf("kubectl port-forward -n %s svc/%s 8080:%d", ns, svcName, portNum)
		}
		if podIP := lookupPodIP(ctx, client, ns, nid); podIP != "" {
			metaBase["actual_runtime_ip"] = podIP
		}
		accessResources = append(accessResources, model.RuntimeAccessResource{
			Type:               "node",
			NodeID:             nid,
			Name:               strings.TrimSpace(pn.Name),
			RuntimeName:        dname,
			Status:             "running",
			NamespaceOrNetwork: ns,
			Ports:              ports,
			InternalURL:        internalURL,
			Metadata:           metaBase,
		})
		svcMeta := map[string]string{
			"dns":                  fmt.Sprintf("%s.%s.svc.cluster.local", svcName, ns),
			"cluster_service_type": string(svcType),
		}
		if svcType == corev1.ServiceTypeNodePort {
			svcMeta["public_access"] = "nodeport"
			svcMeta["exposure_mode"] = "nodeport"
		} else {
			svcMeta["public_access"] = "internal_only"
			svcMeta["exposure_mode"] = "clusterip"
			svcMeta["manual_port_forward_cmd"] = fmt.Sprintf("kubectl port-forward -n %s svc/%s 8080:%d", ns, svcName, portNum)
		}
		for k, v := range metaBase {
			svcMeta[k] = v
		}
		accessResources = append(accessResources, model.RuntimeAccessResource{
			Type:               "service",
			ServiceID:          nid,
			Name:               strings.TrimSpace(pn.Name),
			RuntimeName:        svcName,
			Status:             "running",
			NamespaceOrNetwork: ns,
			Ports:              ports,
			InternalURL:        internalURL,
			Metadata:           svcMeta,
		})
	}

	events = append(events, ev("info", "Kubernetes deployment completed successfully"))
	ra := &model.RuntimeAccess{
		DeploymentID:       strings.TrimSpace(req.DeploymentID),
		TopologyID:         strings.TrimSpace(req.TopologyID),
		Status:             "running",
		RuntimeProvider:    "kubernetes",
		NamespaceOrNetwork: ns,
		Resources:          accessResources,
	}
	return model.DeploymentResponse{
		Status:          "succeeded",
		RuntimeProvider: "kubernetes",
		Events:          events,
		RuntimeAccess:   ra,
	}
}

func clusterInternalServiceURL(namespace, svc string, port int) string {
	return fmt.Sprintf("http://%s.%s.svc.cluster.local:%d", svc, namespace, port)
}

func int32Ptr(i int32) *int32 { return &i }
