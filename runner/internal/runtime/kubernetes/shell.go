package kubernetes

var shellCandidates = []string{"/bin/sh", "sh", "/bin/bash", "bash"}

// ShellCandidates returns preferred interactive shells for exec/terminal attach.
func ShellCandidates() []string {
	out := make([]string, len(shellCandidates))
	copy(out, shellCandidates)
	return out
}
