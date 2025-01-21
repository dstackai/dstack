package types

type TerminationReason string

const (
	TerminationReasonExecutorError            TerminationReason = "executor_error"
	TerminationReasonCreatingContainerError   TerminationReason = "creating_container_error"
	TerminationReasonContainerExitedWithError TerminationReason = "container_exited_with_error"
	TerminationReasonDoneByRunner             TerminationReason = "done_by_runner"
	TerminationReasonTerminatedByUser         TerminationReason = "terminated_by_user"
	TerminationReasonTerminatedByServer       TerminationReason = "terminated_by_server"
	TerminationReasonMaxDurationExceeded      TerminationReason = "max_duration_exceeded"
)

type JobState string

const (
	JobStateDone        JobState = "done"
	JobStateFailed      JobState = "failed"
	JobStateRunning     JobState = "running"
	JobStateTerminated  JobState = "terminated"
	JobStateTerminating JobState = "terminating"
)
