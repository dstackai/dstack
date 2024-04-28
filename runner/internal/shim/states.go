package shim

type RunnerStatus string

const (
	Pending  RunnerStatus = "pending"
	Pulling  RunnerStatus = "pulling"
	Creating RunnerStatus = "creating"
	Running  RunnerStatus = "running"
)
