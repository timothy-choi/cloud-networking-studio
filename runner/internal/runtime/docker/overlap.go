package docker

import (
	"fmt"
	"net"
	"strings"

	docker "github.com/fsouza/go-dockerclient"
)

const dockerSubnetOverlapMessage = "Docker network subnet overlaps with an existing network. " +
	"CNS attempted cleanup/retry but could not allocate a network."

const intentSubnetOverlapMessage = "Requested topology subnet overlaps with existing Docker network. " +
	"Use managed mode or choose a different subnet."

func listEngineIPv4Networks(cli *docker.Client) ([]*net.IPNet, error) {
	nets, err := cli.ListNetworks()
	if err != nil {
		return nil, err
	}
	var out []*net.IPNet
	for _, n := range nets {
		for _, cfg := range n.IPAM.Config {
			s := strings.TrimSpace(cfg.Subnet)
			if s == "" {
				continue
			}
			_, ipn, err := net.ParseCIDR(s)
			if err != nil || ipn == nil || ipn.IP.To4() == nil {
				continue
			}
			out = append(out, ipn)
		}
	}
	return out, nil
}

func cidrOverlapsUsed(c *net.IPNet, used []*net.IPNet) bool {
	for _, u := range used {
		if u == nil || c == nil {
			continue
		}
		if cidrOverlap(c, u) {
			return true
		}
	}
	return false
}

func lastIPv4InNet(n *net.IPNet) net.IP {
	if n.IP.To4() == nil {
		return nil
	}
	ip := make(net.IP, len(n.IP.To4()))
	copy(ip, n.IP.To4())
	for i := range ip {
		ip[i] |= ^n.Mask[i]
	}
	return ip
}

func cidrOverlap(a, b *net.IPNet) bool {
	if a.IP.To4() == nil || b.IP.To4() == nil {
		return false
	}
	aLast := lastIPv4InNet(a)
	bLast := lastIPv4InNet(b)
	if aLast == nil || bLast == nil {
		return false
	}
	return a.Contains(b.IP) || a.Contains(bLast) || b.Contains(a.IP) || b.Contains(aLast)
}

func isIntentMode(mode string) bool {
	switch strings.TrimSpace(strings.ToLower(mode)) {
	case "intent", "intent_ips", "static":
		return true
	default:
		return false
	}
}

func pickFallbackSlash24(used []*net.IPNet) *net.IPNet {
	seconds := []int{201, 202, 203, 88, 89, 90}
	for _, b := range seconds {
		for c := 0; c < 256; c++ {
			_, ipn, err := net.ParseCIDR(fmt.Sprintf("10.%d.%d.0/24", b, c))
			if err != nil {
				continue
			}
			if !cidrOverlapsUsed(ipn, used) {
				return ipn
			}
		}
	}
	for c := 0; c < 256; c++ {
		_, ipn, err := net.ParseCIDR(fmt.Sprintf("172.30.%d.0/24", c))
		if err != nil {
			continue
		}
		if !cidrOverlapsUsed(ipn, used) {
			return ipn
		}
	}
	return nil
}

// resolveBridgeSubnet returns a /24 CIDR string for Docker IPAM, an optional info message, or empty if exhausted.
func resolveBridgeSubnet(cli *docker.Client, preferred string, intentMode bool) (string, string, error) {
	used, err := listEngineIPv4Networks(cli)
	if err != nil {
		return "", "", err
	}
	_, pref, err := net.ParseCIDR(strings.TrimSpace(preferred))
	if err != nil {
		return preferred, "", nil
	}
	if pref.IP.To4() == nil {
		return preferred, "", nil
	}
	if !cidrOverlapsUsed(pref, used) {
		return pref.String(), "", nil
	}
	if intentMode {
		return "", "", fmt.Errorf("%w", errSubnetOverlap)
	}
	ones, bits := pref.Mask.Size()
	if bits != 32 || ones != 24 {
		return "", "", fmt.Errorf("%w", errSubnetOverlap)
	}
	fb := pickFallbackSlash24(used)
	if fb == nil {
		return "", "", fmt.Errorf("%w", errSubnetOverlap)
	}
	return fb.String(), fmt.Sprintf("Docker subnet %s overlaps an existing network; using alternate %s.", pref.String(), fb.String()), nil
}

type subnetOverlapErr struct{}

func (subnetOverlapErr) Error() string { return "subnet overlap" }

var errSubnetOverlap = subnetOverlapErr{}
