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
	// Setup must be called once, before Run. Run must not be called if it fails
	Setup(ctx context.Context) error
	// JobInfo must be called after a successful Setup
	JobInfo() (username string, workingDir string)
	// Run finalizes the executor before returning
	Run(ctx context.Context) error
	// It must be safe to call Finalize more than once
	Finalize(ctx context.Context)

	GetHistory(timestamp int64) *schemas.PullResponse
	GetJobWsLogsHistory() []schemas.LogEvent

	GetRunnerState() string
	SetRunnerState(state string)

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
