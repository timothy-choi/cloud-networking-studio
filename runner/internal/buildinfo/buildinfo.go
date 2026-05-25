// Package buildinfo exposes runner version metadata (overridable at link time).
package buildinfo

// Set via -ldflags, e.g.:
// -X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.Version=1.2.3
var (
	Version   = "dev"
	GitSHA    = "unknown"
	BuildTime = "unknown"
)
