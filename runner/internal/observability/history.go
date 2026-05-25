package observability

import (
	"sync"
	"time"
)

const maxHistory = 100
const staleAfter = 5 * time.Minute

// OperationRecord is one traced runner HTTP operation.
type OperationRecord struct {
	Operation    string    `json:"operation"`
	Provider     string    `json:"provider"`
	Status       string    `json:"status"`
	DurationMs   int64     `json:"duration_ms"`
	RequestID    string    `json:"request_id,omitempty"`
	DeploymentID string    `json:"deployment_id,omitempty"`
	TopologyID   string    `json:"topology_id,omitempty"`
	ErrorMessage string    `json:"error_message,omitempty"`
	StatusCode   int       `json:"status_code,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
}

var (
	mu             sync.Mutex
	lastRuntimeErr string
	lastRuntimeAt  time.Time
	records        []OperationRecord
)

var probeOperations = map[string]struct{}{
	"status":         {},
	"runtime_status": {},
	"runner_status":  {},
	"health":         {},
	"version":        {},
}

// SetLastRuntimeError stores the most recent runtime failure (non-secret).
func SetLastRuntimeError(msg string) {
	mu.Lock()
	defer mu.Unlock()
	lastRuntimeErr = msg
	lastRuntimeAt = time.Now().UTC()
}

// LastRuntimeError returns the stored error message when still active.
func LastRuntimeError() string {
	mu.Lock()
	defer mu.Unlock()
	if lastRuntimeErr == "" {
		return ""
	}
	if time.Since(lastRuntimeAt) > staleAfter {
		return ""
	}
	return lastRuntimeErr
}

// ClearLastRuntimeErrorIfProbe clears probe-related errors after a successful status check.
func ClearLastRuntimeErrorIfProbe(operation string) {
	mu.Lock()
	defer mu.Unlock()
	if _, ok := probeOperations[operation]; !ok {
		return
	}
	lastRuntimeErr = ""
}

// RecordOperation appends a history row (ring buffer).
func RecordOperation(rec OperationRecord) {
	mu.Lock()
	defer mu.Unlock()
	if rec.CreatedAt.IsZero() {
		rec.CreatedAt = time.Now().UTC()
	}
	records = append(records, rec)
	if len(records) > maxHistory {
		records = records[len(records)-maxHistory:]
	}
	if rec.Status != "ok" && rec.ErrorMessage != "" {
		lastRuntimeErr = rec.ErrorMessage
		lastRuntimeAt = rec.CreatedAt
	}
}

// RecentOperations returns the newest records first.
func RecentOperations(limit int) []OperationRecord {
	mu.Lock()
	defer mu.Unlock()
	if limit <= 0 || limit > len(records) {
		limit = len(records)
	}
	out := make([]OperationRecord, 0, limit)
	for i := len(records) - 1; i >= 0 && len(out) < limit; i-- {
		out = append(out, records[i])
	}
	return out
}
