package executor

import (
	"context"

	"github.com/dstackai/dstack/runner/internal/schemas"
	"github.com/dstackai/dstack/runner/internal/types"
)

type Executor interface {
	GetHistory(timestamp int64) *schemas.PullResponse
	GetJobLogsHistory() []schemas.LogEvent
	GetRunnerState() string
	Run(ctx context.Context) error
	SetCodePath(codePath string)
	SetJob(job schemas.SubmitBody)
	SetJobState(ctx context.Context, state types.JobState)
	SetJobStateWithTerminationReason(
		ctx context.Context,
		state types.JobState,
		termination_reason types.TerminationReason,
		termination_message string,
	)
	SetRunnerState(state string)
	Lock()
	RLock()
	RUnlock()
	Unlock()
}
