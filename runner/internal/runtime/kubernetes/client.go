package kubernetes

import (
	"os"
	"strings"

	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"
)

// NewClientset builds a Kubernetes clientset from kubeconfig (local kind/minikube) or in-cluster config.
// Returns REST config (for exec), current kubeconfig context name (best-effort), and error.
func NewClientset() (kubernetes.Interface, *rest.Config, string, error) {
	if cfg, err := rest.InClusterConfig(); err == nil {
		cs, err2 := kubernetes.NewForConfig(cfg)
		if err2 != nil {
			return nil, nil, "", err2
		}
		return cs, cfg, "in-cluster", nil
	}
	loadingRules := clientcmd.NewDefaultClientConfigLoadingRules()
	if p := strings.TrimSpace(os.Getenv("KUBECONFIG")); p != "" {
		loadingRules.ExplicitPath = p
	}
	kc := clientcmd.NewNonInteractiveDeferredLoadingClientConfig(loadingRules, &clientcmd.ConfigOverrides{})
	raw, err := kc.RawConfig()
	cur := ""
	if err == nil {
		cur = raw.CurrentContext
	}
	restCfg, err := kc.ClientConfig()
	if err != nil {
		return nil, nil, cur, err
	}
	cs, err := kubernetes.NewForConfig(restCfg)
	if err != nil {
		return nil, nil, cur, err
	}
	return cs, restCfg, cur, nil
}