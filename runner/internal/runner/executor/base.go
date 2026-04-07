package executor

import (
	"context"
	"io"

	"github.com/dstackai/dstack/runner/internal/common/types"
	"github.com/dstackai/dstack/runner/internal/runner/schemas"
)

type Executor interface {
	// It must be safe to call SetJob more than once
	SetJob(job schemas.SubmitBody)
	// It must be safe to call WriteFileArchive more than once with the same archive
	WriteFileArchive(id string, src io.Reader) error
	// It must be safe to call WriteRepoBlob more than once
	WriteRepoBlob(src io.Reader) error
	Run(ctx context.Context) error

	GetHistory(timestamp int64) *schemas.PullResponse
	GetJobWsLogsHistory() []schemas.LogEvent

	GetRunnerState() string
	SetRunnerState(state string)

	GetJobInfo(ctx context.Context) (username string, workingDir string, err error)
	SetJobState(ctx context.Context, state schemas.JobState)
	SetJobStateWithTerminationReason(
		ctx context.Context,
		state schemas.JobState,
		terminationReason types.TerminationReason,
		terminationMessage string,
	)

	Lock()
	RLock()
	RUnlock()
	Unlock()
}
