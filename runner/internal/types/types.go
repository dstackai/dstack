package types

type TerminationReason string

const (
	TerminationReasonExecutorError            TerminationReason = "EXECUTOR_ERROR"
	TerminationReasonCreatingContainerError   TerminationReason = "CREATING_CONTAINER_ERROR"
	TerminationReasonContainerExitedWithError TerminationReason = "CONTAINER_EXITED_WITH_ERROR"
	TerminationReasonDoneByRunner             TerminationReason = "DONE_BY_RUNNER"
	TerminationReasonTerminatedByUser         TerminationReason = "TERMINATED_BY_USER"
	TerminationReasonTerminatedByServer       TerminationReason = "TERMINATED_BY_SERVER"
)

type JobState string

const (
	JobStateDone        JobState = "done"
	JobStateFailed      JobState = "failed"
	JobStateRunning     JobState = "running"
	JobStateTerminated  JobState = "terminated"
	JobStateTerminating JobState = "terminating"
)
