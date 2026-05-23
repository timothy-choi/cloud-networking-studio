package kubernetes

import (
	"os"
	"strings"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// ClientMeta describes how the Kubernetes client was built.
type ClientMeta struct {
	Source         string // in-cluster, kubeconfig path, or default
	Context        string
	ServerURL      string
	LocalDevCluster bool
}

// NewClientset builds a Kubernetes clientset from kubeconfig or in-cluster config.
func NewClientset() (kubernetes.Interface, *rest.Config, string, error) {
	cs, cfg, meta, err := NewClientsetWithMeta()
	if err != nil {
		return nil, nil, meta.Context, err
	}
	return cs, cfg, meta.Context, nil
}

// NewClientsetWithMeta returns client metadata for status reporting.
func NewClientsetWithMeta() (kubernetes.Interface, *rest.Config, ClientMeta, error) {
	meta := ClientMeta{}
	if cfg, err := rest.InClusterConfig(); err == nil {
		cs, err2 := kubernetes.NewForConfig(cfg)
		if err2 != nil {
			return nil, nil, meta, err2
		}
		meta.Source = "in-cluster"
		meta.Context = "in-cluster"
		meta.ServerURL = strings.TrimSpace(cfg.Host)
		meta.LocalDevCluster = isLocalDevServer(meta.ServerURL)
		return cs, cfg, meta, nil
	}
	loadingRules := clientcmd.NewDefaultClientConfigLoadingRules()
	if p := strings.TrimSpace(os.Getenv("KUBECONFIG")); p != "" {
		loadingRules.ExplicitPath = p
		meta.Source = p
	} else {
		meta.Source = "default-kubeconfig"
	}
	kc := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loadingRules, &clientcmd.ConfigOverrides{})
	raw, err := kc.RawConfig()
	if err == nil {
		meta.Context = raw.CurrentContext
		if meta.Source == "default-kubeconfig" && len(loadingRules.Precedence) > 0 {
			meta.Source = loadingRules.Precedence[0]
		}
	}
	restCfg, err := kc.ClientConfig()
	if err != nil {
		return nil, nil, meta, err
	}
	meta.ServerURL = strings.TrimSpace(restCfg.Host)
	meta.LocalDevCluster = isLocalDevServer(meta.ServerURL) || isLocalDevContext(meta.Context)
	cs, err := kubernetes.NewForConfig(restCfg)
	if err != nil {
		return nil, nil, meta, err
	}
	return cs, restCfg, meta, nil
}

func isLocalDevServer(serverURL string) bool {
	s := strings.ToLower(strings.TrimSpace(serverURL))
	if s == "" {
		return false
	}
	return strings.Contains(s, "host.docker.internal") ||
		strings.Contains(s, "127.0.0.1") ||
		strings.Contains(s, "localhost") ||
		strings.Contains(s, "0.0.0.0")
}

func isLocalDevContext(ctx string) bool {
	c := strings.ToLower(strings.TrimSpace(ctx))
	if c == "" {
		return false
	}
	return strings.Contains(c, "kind-") ||
		strings.Contains(c, "minikube") ||
		strings.Contains(c, "docker-desktop") ||
		strings.Contains(c, "k3d-")
}

// ProductionBlocked returns a message when local dev clusters must not run in production.
func ProductionBlocked(meta ClientMeta, environment string) string {
	env := strings.ToLower(strings.TrimSpace(environment))
	if env != "production" {
		return ""
	}
	if meta.LocalDevCluster || isLocalDevContext(meta.Context) {
		return "local/kind/minikube cluster contexts are not allowed when CNS_ENVIRONMENT=production; use Docker (default) or a production cluster kubeconfig"
	}
	return ""
}
