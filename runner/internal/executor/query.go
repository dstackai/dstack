package executor

import (
	"github.com/dstackai/dstack/runner/internal/schemas"
)

func (ex *RunExecutor) GetJobWsLogsHistory() []schemas.LogEvent {
	return ex.jobWsLogs.history
}

func (ex *RunExecutor) GetHistory(timestamp int64) *schemas.PullResponse {
	return &schemas.PullResponse{
		JobStates:         eventsAfter(ex.jobStateHistory, timestamp),
		JobLogs:           eventsAfter(ex.jobLogs.history, timestamp),
		RunnerLogs:        eventsAfter(ex.runnerLogs.history, timestamp),
		LastUpdated:       ex.timestamp.GetLatest(),
		NoConnectionsSecs: ex.connectionTracker.GetNoConnectionsSecs(),
		HasMore:           ex.state != WaitLogsFinished,
	}
}

func (ex *RunExecutor) GetRunnerState() string {
	return ex.state
}

type OrderedEvent interface {
	GetTimestamp() int64
}

func eventsAfter[T OrderedEvent](events []T, timestamp int64) []T {
	left := 0
	right := len(events)
	for left < right {
		mid := (left + right) / 2
		if events[mid].GetTimestamp() <= timestamp {
			left = mid + 1
		} else {
			right = mid
		}
	}
	return events[left:]
}
