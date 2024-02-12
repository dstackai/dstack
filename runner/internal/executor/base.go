package executor

import (
	"context"

	"github.com/dstackai/dstack/runner/internal/schemas"
)

type Executor interface {
	GetHistory(timestamp int64) *schemas.PullResponse
	GetJobLogsHistory() []schemas.LogEvent
	GetRunnerState() string
	Run(ctx context.Context) error
	SetCodePath(codePath string)
	SetJob(job schemas.SubmitBody)
	SetJobState(ctx context.Context, state string)
	SetRunnerState(state string)
	Lock()
	RLock()
	RUnlock()
	Unlock()
}
