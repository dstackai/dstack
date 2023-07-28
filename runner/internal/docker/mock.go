package docker

import (
	"context"
	"io"
	"net"
	"net/http"
	"time"

	"github.com/docker/docker/api/types"
	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/events"
	"github.com/docker/docker/api/types/filters"
	"github.com/docker/docker/api/types/image"
	"github.com/docker/docker/api/types/network"
	"github.com/docker/docker/api/types/registry"
	"github.com/docker/docker/api/types/swarm"
	"github.com/docker/docker/api/types/volume"
	"github.com/docker/docker/client"
	v1 "github.com/opencontainers/image-spec/specs-go/v1"
	"github.com/stretchr/testify/mock"
)

var _ client.APIClient = (*MockClient)(nil)

type MockClient struct {
	mock.Mock
}

func (mock *MockClient) BuildCachePrune(ctx context.Context, opts types.BuildCachePruneOptions) (*types.BuildCachePruneReport, error) {
	ret := mock.Called(ctx, opts)

	var r0 *types.BuildCachePruneReport
	if rf, ok := ret.Get(0).(func(context.Context, types.BuildCachePruneOptions) *types.BuildCachePruneReport); ok {
		r0 = rf(ctx, opts)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(*types.BuildCachePruneReport)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.BuildCachePruneOptions) error); ok {
		r1 = rf(ctx, opts)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) BuildCancel(ctx context.Context, id string) error {
	ret := mock.Called(ctx, id)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, id)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) CheckpointCreate(ctx context.Context, _a1 string, options types.CheckpointCreateOptions) error {
	ret := mock.Called(ctx, _a1, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.CheckpointCreateOptions) error); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) CheckpointDelete(ctx context.Context, _a1 string, options types.CheckpointDeleteOptions) error {
	ret := mock.Called(ctx, _a1, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.CheckpointDeleteOptions) error); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) CheckpointList(ctx context.Context, _a1 string, options types.CheckpointListOptions) ([]types.Checkpoint, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 []types.Checkpoint
	if rf, ok := ret.Get(0).(func(context.Context, string, types.CheckpointListOptions) []types.Checkpoint); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]types.Checkpoint)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.CheckpointListOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ClientVersion() string {
	ret := mock.Called()

	var r0 string
	if rf, ok := ret.Get(0).(func() string); ok {
		r0 = rf()
	} else {
		r0 = ret.Get(0).(string)
	}

	return r0
}

func (mock *MockClient) Close() error {
	ret := mock.Called()

	var r0 error
	if rf, ok := ret.Get(0).(func() error); ok {
		r0 = rf()
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ConfigCreate(ctx context.Context, config swarm.ConfigSpec) (types.ConfigCreateResponse, error) {
	ret := mock.Called(ctx, config)

	var r0 types.ConfigCreateResponse
	if rf, ok := ret.Get(0).(func(context.Context, swarm.ConfigSpec) types.ConfigCreateResponse); ok {
		r0 = rf(ctx, config)
	} else {
		r0 = ret.Get(0).(types.ConfigCreateResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, swarm.ConfigSpec) error); ok {
		r1 = rf(ctx, config)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ConfigInspectWithRaw(ctx context.Context, name string) (swarm.Config, []byte, error) {
	ret := mock.Called(ctx, name)

	var r0 swarm.Config
	if rf, ok := ret.Get(0).(func(context.Context, string) swarm.Config); ok {
		r0 = rf(ctx, name)
	} else {
		r0 = ret.Get(0).(swarm.Config)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, name)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, name)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) ConfigList(ctx context.Context, options types.ConfigListOptions) ([]swarm.Config, error) {
	ret := mock.Called(ctx, options)

	var r0 []swarm.Config
	if rf, ok := ret.Get(0).(func(context.Context, types.ConfigListOptions) []swarm.Config); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]swarm.Config)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.ConfigListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ConfigRemove(ctx context.Context, id string) error {
	ret := mock.Called(ctx, id)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, id)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ConfigUpdate(ctx context.Context, id string, version swarm.Version, config swarm.ConfigSpec) error {
	ret := mock.Called(ctx, id, version, config)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, swarm.Version, swarm.ConfigSpec) error); ok {
		r0 = rf(ctx, id, version, config)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerAttach(ctx context.Context, _a1 string, options types.ContainerAttachOptions) (types.HijackedResponse, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 types.HijackedResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerAttachOptions) types.HijackedResponse); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Get(0).(types.HijackedResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ContainerAttachOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerCommit(ctx context.Context, _a1 string, options types.ContainerCommitOptions) (types.IDResponse, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 types.IDResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerCommitOptions) types.IDResponse); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Get(0).(types.IDResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ContainerCommitOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerCreate(ctx context.Context, config *container.Config, hostConfig *container.HostConfig, networkingConfig *network.NetworkingConfig, platform *v1.Platform, containerName string) (container.ContainerCreateCreatedBody, error) {
	ret := mock.Called(ctx, config, hostConfig, networkingConfig, platform, containerName)

	var r0 container.ContainerCreateCreatedBody
	if rf, ok := ret.Get(0).(func(context.Context, *container.Config, *container.HostConfig, *network.NetworkingConfig, *v1.Platform, string) container.ContainerCreateCreatedBody); ok {
		r0 = rf(ctx, config, hostConfig, networkingConfig, platform, containerName)
	} else {
		r0 = ret.Get(0).(container.ContainerCreateCreatedBody)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, *container.Config, *container.HostConfig, *network.NetworkingConfig, *v1.Platform, string) error); ok {
		r1 = rf(ctx, config, hostConfig, networkingConfig, platform, containerName)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerDiff(ctx context.Context, _a1 string) ([]container.ContainerChangeResponseItem, error) {
	ret := mock.Called(ctx, _a1)

	var r0 []container.ContainerChangeResponseItem
	if rf, ok := ret.Get(0).(func(context.Context, string) []container.ContainerChangeResponseItem); ok {
		r0 = rf(ctx, _a1)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]container.ContainerChangeResponseItem)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, _a1)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerExecAttach(ctx context.Context, execID string, config types.ExecStartCheck) (types.HijackedResponse, error) {
	ret := mock.Called(ctx, execID, config)

	var r0 types.HijackedResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ExecStartCheck) types.HijackedResponse); ok {
		r0 = rf(ctx, execID, config)
	} else {
		r0 = ret.Get(0).(types.HijackedResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ExecStartCheck) error); ok {
		r1 = rf(ctx, execID, config)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerExecCreate(ctx context.Context, _a1 string, config types.ExecConfig) (types.IDResponse, error) {
	ret := mock.Called(ctx, _a1, config)

	var r0 types.IDResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ExecConfig) types.IDResponse); ok {
		r0 = rf(ctx, _a1, config)
	} else {
		r0 = ret.Get(0).(types.IDResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ExecConfig) error); ok {
		r1 = rf(ctx, _a1, config)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerExecInspect(ctx context.Context, execID string) (types.ContainerExecInspect, error) {
	ret := mock.Called(ctx, execID)

	var r0 types.ContainerExecInspect
	if rf, ok := ret.Get(0).(func(context.Context, string) types.ContainerExecInspect); ok {
		r0 = rf(ctx, execID)
	} else {
		r0 = ret.Get(0).(types.ContainerExecInspect)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, execID)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerExecResize(ctx context.Context, execID string, options types.ResizeOptions) error {
	ret := mock.Called(ctx, execID, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ResizeOptions) error); ok {
		r0 = rf(ctx, execID, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerExecStart(ctx context.Context, execID string, config types.ExecStartCheck) error {
	ret := mock.Called(ctx, execID, config)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ExecStartCheck) error); ok {
		r0 = rf(ctx, execID, config)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerExport(ctx context.Context, _a1 string) (io.ReadCloser, error) {
	ret := mock.Called(ctx, _a1)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string) io.ReadCloser); ok {
		r0 = rf(ctx, _a1)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, _a1)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerInspect(ctx context.Context, _a1 string) (types.ContainerJSON, error) {
	ret := mock.Called(ctx, _a1)

	var r0 types.ContainerJSON
	if rf, ok := ret.Get(0).(func(context.Context, string) types.ContainerJSON); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Get(0).(types.ContainerJSON)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, _a1)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerInspectWithRaw(ctx context.Context, _a1 string, getSize bool) (types.ContainerJSON, []byte, error) {
	ret := mock.Called(ctx, _a1, getSize)

	var r0 types.ContainerJSON
	if rf, ok := ret.Get(0).(func(context.Context, string, bool) types.ContainerJSON); ok {
		r0 = rf(ctx, _a1, getSize)
	} else {
		r0 = ret.Get(0).(types.ContainerJSON)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string, bool) []byte); ok {
		r1 = rf(ctx, _a1, getSize)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string, bool) error); ok {
		r2 = rf(ctx, _a1, getSize)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) ContainerKill(ctx context.Context, _a1 string, signal string) error {
	ret := mock.Called(ctx, _a1, signal)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string) error); ok {
		r0 = rf(ctx, _a1, signal)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerList(ctx context.Context, options types.ContainerListOptions) ([]types.Container, error) {
	ret := mock.Called(ctx, options)

	var r0 []types.Container
	if rf, ok := ret.Get(0).(func(context.Context, types.ContainerListOptions) []types.Container); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]types.Container)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.ContainerListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerLogs(ctx context.Context, _a1 string, options types.ContainerLogsOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerLogsOptions) io.ReadCloser); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ContainerLogsOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerPause(ctx context.Context, _a1 string) error {
	ret := mock.Called(ctx, _a1)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerRemove(ctx context.Context, _a1 string, options types.ContainerRemoveOptions) error {
	ret := mock.Called(ctx, _a1, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerRemoveOptions) error); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerRename(ctx context.Context, _a1 string, newContainerName string) error {
	ret := mock.Called(ctx, _a1, newContainerName)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string) error); ok {
		r0 = rf(ctx, _a1, newContainerName)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerResize(ctx context.Context, _a1 string, options types.ResizeOptions) error {
	ret := mock.Called(ctx, _a1, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ResizeOptions) error); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerRestart(ctx context.Context, _a1 string, timeout *time.Duration) error {
	ret := mock.Called(ctx, _a1, timeout)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, *time.Duration) error); ok {
		r0 = rf(ctx, _a1, timeout)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerStart(ctx context.Context, _a1 string, options types.ContainerStartOptions) error {
	ret := mock.Called(ctx, _a1, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerStartOptions) error); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerStatPath(ctx context.Context, _a1 string, path string) (types.ContainerPathStat, error) {
	ret := mock.Called(ctx, _a1, path)

	var r0 types.ContainerPathStat
	if rf, ok := ret.Get(0).(func(context.Context, string, string) types.ContainerPathStat); ok {
		r0 = rf(ctx, _a1, path)
	} else {
		r0 = ret.Get(0).(types.ContainerPathStat)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, string) error); ok {
		r1 = rf(ctx, _a1, path)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerStats(ctx context.Context, _a1 string, stream bool) (types.ContainerStats, error) {
	ret := mock.Called(ctx, _a1, stream)

	var r0 types.ContainerStats
	if rf, ok := ret.Get(0).(func(context.Context, string, bool) types.ContainerStats); ok {
		r0 = rf(ctx, _a1, stream)
	} else {
		r0 = ret.Get(0).(types.ContainerStats)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, bool) error); ok {
		r1 = rf(ctx, _a1, stream)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerStatsOneShot(ctx context.Context, _a1 string) (types.ContainerStats, error) {
	ret := mock.Called(ctx, _a1)

	var r0 types.ContainerStats
	if rf, ok := ret.Get(0).(func(context.Context, string) types.ContainerStats); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Get(0).(types.ContainerStats)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, _a1)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerStop(ctx context.Context, _a1 string, timeout *time.Duration) error {
	ret := mock.Called(ctx, _a1, timeout)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, *time.Duration) error); ok {
		r0 = rf(ctx, _a1, timeout)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerTop(ctx context.Context, _a1 string, arguments []string) (container.ContainerTopOKBody, error) {
	ret := mock.Called(ctx, _a1, arguments)

	var r0 container.ContainerTopOKBody
	if rf, ok := ret.Get(0).(func(context.Context, string, []string) container.ContainerTopOKBody); ok {
		r0 = rf(ctx, _a1, arguments)
	} else {
		r0 = ret.Get(0).(container.ContainerTopOKBody)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, []string) error); ok {
		r1 = rf(ctx, _a1, arguments)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerUnpause(ctx context.Context, _a1 string) error {
	ret := mock.Called(ctx, _a1)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ContainerUpdate(ctx context.Context, _a1 string, updateConfig container.UpdateConfig) (container.ContainerUpdateOKBody, error) {
	ret := mock.Called(ctx, _a1, updateConfig)

	var r0 container.ContainerUpdateOKBody
	if rf, ok := ret.Get(0).(func(context.Context, string, container.UpdateConfig) container.ContainerUpdateOKBody); ok {
		r0 = rf(ctx, _a1, updateConfig)
	} else {
		r0 = ret.Get(0).(container.ContainerUpdateOKBody)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, container.UpdateConfig) error); ok {
		r1 = rf(ctx, _a1, updateConfig)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ContainerWait(ctx context.Context, _a1 string, condition container.WaitCondition) (<-chan container.ContainerWaitOKBody, <-chan error) {
	ret := mock.Called(ctx, _a1, condition)

	var r0 <-chan container.ContainerWaitOKBody
	if rf, ok := ret.Get(0).(func(context.Context, string, container.WaitCondition) <-chan container.ContainerWaitOKBody); ok {
		r0 = rf(ctx, _a1, condition)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(<-chan container.ContainerWaitOKBody)
		}
	}

	var r1 <-chan error
	if rf, ok := ret.Get(1).(func(context.Context, string, container.WaitCondition) <-chan error); ok {
		r1 = rf(ctx, _a1, condition)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).(<-chan error)
		}
	}

	return r0, r1
}

func (mock *MockClient) ContainersPrune(ctx context.Context, pruneFilters filters.Args) (types.ContainersPruneReport, error) {
	ret := mock.Called(ctx, pruneFilters)

	var r0 types.ContainersPruneReport
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) types.ContainersPruneReport); ok {
		r0 = rf(ctx, pruneFilters)
	} else {
		r0 = ret.Get(0).(types.ContainersPruneReport)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, pruneFilters)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) CopyFromContainer(ctx context.Context, _a1 string, srcPath string) (io.ReadCloser, types.ContainerPathStat, error) {
	ret := mock.Called(ctx, _a1, srcPath)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, string) io.ReadCloser); ok {
		r0 = rf(ctx, _a1, srcPath)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 types.ContainerPathStat
	if rf, ok := ret.Get(1).(func(context.Context, string, string) types.ContainerPathStat); ok {
		r1 = rf(ctx, _a1, srcPath)
	} else {
		r1 = ret.Get(1).(types.ContainerPathStat)
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string, string) error); ok {
		r2 = rf(ctx, _a1, srcPath)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) CopyToContainer(ctx context.Context, _a1 string, path string, content io.Reader, options types.CopyToContainerOptions) error {
	ret := mock.Called(ctx, _a1, path, content, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string, io.Reader, types.CopyToContainerOptions) error); ok {
		r0 = rf(ctx, _a1, path, content, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) DaemonHost() string {
	ret := mock.Called()

	var r0 string
	if rf, ok := ret.Get(0).(func() string); ok {
		r0 = rf()
	} else {
		r0 = ret.Get(0).(string)
	}

	return r0
}

func (mock *MockClient) DialHijack(ctx context.Context, url string, proto string, meta map[string][]string) (net.Conn, error) {
	ret := mock.Called(ctx, url, proto, meta)

	var r0 net.Conn
	if rf, ok := ret.Get(0).(func(context.Context, string, string, map[string][]string) net.Conn); ok {
		r0 = rf(ctx, url, proto, meta)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(net.Conn)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, string, map[string][]string) error); ok {
		r1 = rf(ctx, url, proto, meta)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) Dialer() func(context.Context) (net.Conn, error) {
	ret := mock.Called()

	var r0 func(context.Context) (net.Conn, error)
	if rf, ok := ret.Get(0).(func() func(context.Context) (net.Conn, error)); ok {
		r0 = rf()
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(func(context.Context) (net.Conn, error))
		}
	}

	return r0
}

func (mock *MockClient) DiskUsage(ctx context.Context) (types.DiskUsage, error) {
	ret := mock.Called(ctx)

	var r0 types.DiskUsage
	if rf, ok := ret.Get(0).(func(context.Context) types.DiskUsage); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(types.DiskUsage)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) DistributionInspect(ctx context.Context, _a1 string, encodedRegistryAuth string) (registry.DistributionInspect, error) {
	ret := mock.Called(ctx, _a1, encodedRegistryAuth)

	var r0 registry.DistributionInspect
	if rf, ok := ret.Get(0).(func(context.Context, string, string) registry.DistributionInspect); ok {
		r0 = rf(ctx, _a1, encodedRegistryAuth)
	} else {
		r0 = ret.Get(0).(registry.DistributionInspect)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, string) error); ok {
		r1 = rf(ctx, _a1, encodedRegistryAuth)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) Events(ctx context.Context, options types.EventsOptions) (<-chan events.Message, <-chan error) {
	ret := mock.Called(ctx, options)

	var r0 <-chan events.Message
	if rf, ok := ret.Get(0).(func(context.Context, types.EventsOptions) <-chan events.Message); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(<-chan events.Message)
		}
	}

	var r1 <-chan error
	if rf, ok := ret.Get(1).(func(context.Context, types.EventsOptions) <-chan error); ok {
		r1 = rf(ctx, options)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).(<-chan error)
		}
	}

	return r0, r1
}

func (mock *MockClient) HTTPClient() *http.Client {
	ret := mock.Called()

	var r0 *http.Client
	if rf, ok := ret.Get(0).(func() *http.Client); ok {
		r0 = rf()
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(*http.Client)
		}
	}

	return r0
}

func (mock *MockClient) ImageBuild(ctx context.Context, _a1 io.Reader, options types.ImageBuildOptions) (types.ImageBuildResponse, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 types.ImageBuildResponse
	if rf, ok := ret.Get(0).(func(context.Context, io.Reader, types.ImageBuildOptions) types.ImageBuildResponse); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Get(0).(types.ImageBuildResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, io.Reader, types.ImageBuildOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageCreate(ctx context.Context, parentReference string, options types.ImageCreateOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, parentReference, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ImageCreateOptions) io.ReadCloser); ok {
		r0 = rf(ctx, parentReference, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ImageCreateOptions) error); ok {
		r1 = rf(ctx, parentReference, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageHistory(ctx context.Context, _a1 string) ([]image.HistoryResponseItem, error) {
	ret := mock.Called(ctx, _a1)

	var r0 []image.HistoryResponseItem
	if rf, ok := ret.Get(0).(func(context.Context, string) []image.HistoryResponseItem); ok {
		r0 = rf(ctx, _a1)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]image.HistoryResponseItem)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, _a1)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageImport(ctx context.Context, source types.ImageImportSource, ref string, options types.ImageImportOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, source, ref, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, types.ImageImportSource, string, types.ImageImportOptions) io.ReadCloser); ok {
		r0 = rf(ctx, source, ref, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.ImageImportSource, string, types.ImageImportOptions) error); ok {
		r1 = rf(ctx, source, ref, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageInspectWithRaw(ctx context.Context, _a1 string) (types.ImageInspect, []byte, error) {
	ret := mock.Called(ctx, _a1)

	var r0 types.ImageInspect
	if rf, ok := ret.Get(0).(func(context.Context, string) types.ImageInspect); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Get(0).(types.ImageInspect)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, _a1)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, _a1)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) ImageList(ctx context.Context, options types.ImageListOptions) ([]types.ImageSummary, error) {
	ret := mock.Called(ctx, options)

	var r0 []types.ImageSummary
	if rf, ok := ret.Get(0).(func(context.Context, types.ImageListOptions) []types.ImageSummary); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]types.ImageSummary)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.ImageListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageLoad(ctx context.Context, input io.Reader, quiet bool) (types.ImageLoadResponse, error) {
	ret := mock.Called(ctx, input, quiet)

	var r0 types.ImageLoadResponse
	if rf, ok := ret.Get(0).(func(context.Context, io.Reader, bool) types.ImageLoadResponse); ok {
		r0 = rf(ctx, input, quiet)
	} else {
		r0 = ret.Get(0).(types.ImageLoadResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, io.Reader, bool) error); ok {
		r1 = rf(ctx, input, quiet)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImagePull(ctx context.Context, ref string, options types.ImagePullOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, ref, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ImagePullOptions) io.ReadCloser); ok {
		r0 = rf(ctx, ref, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ImagePullOptions) error); ok {
		r1 = rf(ctx, ref, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImagePush(ctx context.Context, ref string, options types.ImagePushOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, ref, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ImagePushOptions) io.ReadCloser); ok {
		r0 = rf(ctx, ref, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ImagePushOptions) error); ok {
		r1 = rf(ctx, ref, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageRemove(ctx context.Context, _a1 string, options types.ImageRemoveOptions) ([]types.ImageDeleteResponseItem, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 []types.ImageDeleteResponseItem
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ImageRemoveOptions) []types.ImageDeleteResponseItem); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]types.ImageDeleteResponseItem)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ImageRemoveOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageSave(ctx context.Context, images []string) (io.ReadCloser, error) {
	ret := mock.Called(ctx, images)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, []string) io.ReadCloser); ok {
		r0 = rf(ctx, images)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, []string) error); ok {
		r1 = rf(ctx, images)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageSearch(ctx context.Context, term string, options types.ImageSearchOptions) ([]registry.SearchResult, error) {
	ret := mock.Called(ctx, term, options)

	var r0 []registry.SearchResult
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ImageSearchOptions) []registry.SearchResult); ok {
		r0 = rf(ctx, term, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]registry.SearchResult)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ImageSearchOptions) error); ok {
		r1 = rf(ctx, term, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ImageTag(ctx context.Context, _a1 string, ref string) error {
	ret := mock.Called(ctx, _a1, ref)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string) error); ok {
		r0 = rf(ctx, _a1, ref)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ImagesPrune(ctx context.Context, pruneFilter filters.Args) (types.ImagesPruneReport, error) {
	ret := mock.Called(ctx, pruneFilter)

	var r0 types.ImagesPruneReport
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) types.ImagesPruneReport); ok {
		r0 = rf(ctx, pruneFilter)
	} else {
		r0 = ret.Get(0).(types.ImagesPruneReport)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, pruneFilter)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) Info(ctx context.Context) (types.Info, error) {
	ret := mock.Called(ctx)

	var r0 types.Info
	if rf, ok := ret.Get(0).(func(context.Context) types.Info); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(types.Info)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NegotiateAPIVersion(ctx context.Context) {
	mock.Called(ctx)
}

func (mock *MockClient) NegotiateAPIVersionPing(_a0 types.Ping) {
	mock.Called(_a0)
}

func (mock *MockClient) NetworkConnect(ctx context.Context, _a1 string, _a2 string, config *network.EndpointSettings) error {
	ret := mock.Called(ctx, _a1, _a2, config)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string, *network.EndpointSettings) error); ok {
		r0 = rf(ctx, _a1, _a2, config)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) NetworkCreate(ctx context.Context, name string, options types.NetworkCreate) (types.NetworkCreateResponse, error) {
	ret := mock.Called(ctx, name, options)

	var r0 types.NetworkCreateResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, types.NetworkCreate) types.NetworkCreateResponse); ok {
		r0 = rf(ctx, name, options)
	} else {
		r0 = ret.Get(0).(types.NetworkCreateResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.NetworkCreate) error); ok {
		r1 = rf(ctx, name, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NetworkDisconnect(ctx context.Context, _a1 string, _a2 string, force bool) error {
	ret := mock.Called(ctx, _a1, _a2, force)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, string, bool) error); ok {
		r0 = rf(ctx, _a1, _a2, force)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) NetworkInspect(ctx context.Context, _a1 string, options types.NetworkInspectOptions) (types.NetworkResource, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 types.NetworkResource
	if rf, ok := ret.Get(0).(func(context.Context, string, types.NetworkInspectOptions) types.NetworkResource); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Get(0).(types.NetworkResource)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.NetworkInspectOptions) error); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NetworkInspectWithRaw(ctx context.Context, _a1 string, options types.NetworkInspectOptions) (types.NetworkResource, []byte, error) {
	ret := mock.Called(ctx, _a1, options)

	var r0 types.NetworkResource
	if rf, ok := ret.Get(0).(func(context.Context, string, types.NetworkInspectOptions) types.NetworkResource); ok {
		r0 = rf(ctx, _a1, options)
	} else {
		r0 = ret.Get(0).(types.NetworkResource)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string, types.NetworkInspectOptions) []byte); ok {
		r1 = rf(ctx, _a1, options)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string, types.NetworkInspectOptions) error); ok {
		r2 = rf(ctx, _a1, options)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) NetworkList(ctx context.Context, options types.NetworkListOptions) ([]types.NetworkResource, error) {
	ret := mock.Called(ctx, options)

	var r0 []types.NetworkResource
	if rf, ok := ret.Get(0).(func(context.Context, types.NetworkListOptions) []types.NetworkResource); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]types.NetworkResource)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.NetworkListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NetworkRemove(ctx context.Context, _a1 string) error {
	ret := mock.Called(ctx, _a1)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, _a1)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) NetworksPrune(ctx context.Context, pruneFilter filters.Args) (types.NetworksPruneReport, error) {
	ret := mock.Called(ctx, pruneFilter)

	var r0 types.NetworksPruneReport
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) types.NetworksPruneReport); ok {
		r0 = rf(ctx, pruneFilter)
	} else {
		r0 = ret.Get(0).(types.NetworksPruneReport)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, pruneFilter)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NodeInspectWithRaw(ctx context.Context, nodeID string) (swarm.Node, []byte, error) {
	ret := mock.Called(ctx, nodeID)

	var r0 swarm.Node
	if rf, ok := ret.Get(0).(func(context.Context, string) swarm.Node); ok {
		r0 = rf(ctx, nodeID)
	} else {
		r0 = ret.Get(0).(swarm.Node)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, nodeID)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, nodeID)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) NodeList(ctx context.Context, options types.NodeListOptions) ([]swarm.Node, error) {
	ret := mock.Called(ctx, options)

	var r0 []swarm.Node
	if rf, ok := ret.Get(0).(func(context.Context, types.NodeListOptions) []swarm.Node); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]swarm.Node)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.NodeListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) NodeRemove(ctx context.Context, nodeID string, options types.NodeRemoveOptions) error {
	ret := mock.Called(ctx, nodeID, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.NodeRemoveOptions) error); ok {
		r0 = rf(ctx, nodeID, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) NodeUpdate(ctx context.Context, nodeID string, version swarm.Version, node swarm.NodeSpec) error {
	ret := mock.Called(ctx, nodeID, version, node)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, swarm.Version, swarm.NodeSpec) error); ok {
		r0 = rf(ctx, nodeID, version, node)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) Ping(ctx context.Context) (types.Ping, error) {
	ret := mock.Called(ctx)

	var r0 types.Ping
	if rf, ok := ret.Get(0).(func(context.Context) types.Ping); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(types.Ping)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) PluginCreate(ctx context.Context, createContext io.Reader, options types.PluginCreateOptions) error {
	ret := mock.Called(ctx, createContext, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, io.Reader, types.PluginCreateOptions) error); ok {
		r0 = rf(ctx, createContext, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) PluginDisable(ctx context.Context, name string, options types.PluginDisableOptions) error {
	ret := mock.Called(ctx, name, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.PluginDisableOptions) error); ok {
		r0 = rf(ctx, name, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) PluginEnable(ctx context.Context, name string, options types.PluginEnableOptions) error {
	ret := mock.Called(ctx, name, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.PluginEnableOptions) error); ok {
		r0 = rf(ctx, name, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) PluginInspectWithRaw(ctx context.Context, name string) (*types.Plugin, []byte, error) {
	ret := mock.Called(ctx, name)

	var r0 *types.Plugin
	if rf, ok := ret.Get(0).(func(context.Context, string) *types.Plugin); ok {
		r0 = rf(ctx, name)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(*types.Plugin)
		}
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, name)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, name)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) PluginInstall(ctx context.Context, name string, options types.PluginInstallOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, name, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.PluginInstallOptions) io.ReadCloser); ok {
		r0 = rf(ctx, name, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.PluginInstallOptions) error); ok {
		r1 = rf(ctx, name, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) PluginList(ctx context.Context, filter filters.Args) (types.PluginsListResponse, error) {
	ret := mock.Called(ctx, filter)

	var r0 types.PluginsListResponse
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) types.PluginsListResponse); ok {
		r0 = rf(ctx, filter)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(types.PluginsListResponse)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, filter)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) PluginPush(ctx context.Context, name string, registryAuth string) (io.ReadCloser, error) {
	ret := mock.Called(ctx, name, registryAuth)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, string) io.ReadCloser); ok {
		r0 = rf(ctx, name, registryAuth)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, string) error); ok {
		r1 = rf(ctx, name, registryAuth)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) PluginRemove(ctx context.Context, name string, options types.PluginRemoveOptions) error {
	ret := mock.Called(ctx, name, options)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, types.PluginRemoveOptions) error); ok {
		r0 = rf(ctx, name, options)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) PluginSet(ctx context.Context, name string, args []string) error {
	ret := mock.Called(ctx, name, args)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, []string) error); ok {
		r0 = rf(ctx, name, args)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) PluginUpgrade(ctx context.Context, name string, options types.PluginInstallOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, name, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.PluginInstallOptions) io.ReadCloser); ok {
		r0 = rf(ctx, name, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.PluginInstallOptions) error); ok {
		r1 = rf(ctx, name, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) RegistryLogin(ctx context.Context, auth types.AuthConfig) (registry.AuthenticateOKBody, error) {
	ret := mock.Called(ctx, auth)

	var r0 registry.AuthenticateOKBody
	if rf, ok := ret.Get(0).(func(context.Context, types.AuthConfig) registry.AuthenticateOKBody); ok {
		r0 = rf(ctx, auth)
	} else {
		r0 = ret.Get(0).(registry.AuthenticateOKBody)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.AuthConfig) error); ok {
		r1 = rf(ctx, auth)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SecretCreate(ctx context.Context, secret swarm.SecretSpec) (types.SecretCreateResponse, error) {
	ret := mock.Called(ctx, secret)

	var r0 types.SecretCreateResponse
	if rf, ok := ret.Get(0).(func(context.Context, swarm.SecretSpec) types.SecretCreateResponse); ok {
		r0 = rf(ctx, secret)
	} else {
		r0 = ret.Get(0).(types.SecretCreateResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, swarm.SecretSpec) error); ok {
		r1 = rf(ctx, secret)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SecretInspectWithRaw(ctx context.Context, name string) (swarm.Secret, []byte, error) {
	ret := mock.Called(ctx, name)

	var r0 swarm.Secret
	if rf, ok := ret.Get(0).(func(context.Context, string) swarm.Secret); ok {
		r0 = rf(ctx, name)
	} else {
		r0 = ret.Get(0).(swarm.Secret)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, name)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, name)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) SecretList(ctx context.Context, options types.SecretListOptions) ([]swarm.Secret, error) {
	ret := mock.Called(ctx, options)

	var r0 []swarm.Secret
	if rf, ok := ret.Get(0).(func(context.Context, types.SecretListOptions) []swarm.Secret); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]swarm.Secret)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.SecretListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SecretRemove(ctx context.Context, id string) error {
	ret := mock.Called(ctx, id)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, id)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) SecretUpdate(ctx context.Context, id string, version swarm.Version, secret swarm.SecretSpec) error {
	ret := mock.Called(ctx, id, version, secret)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, swarm.Version, swarm.SecretSpec) error); ok {
		r0 = rf(ctx, id, version, secret)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ServerVersion(ctx context.Context) (types.Version, error) {
	ret := mock.Called(ctx)

	var r0 types.Version
	if rf, ok := ret.Get(0).(func(context.Context) types.Version); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(types.Version)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ServiceCreate(ctx context.Context, service swarm.ServiceSpec, options types.ServiceCreateOptions) (types.ServiceCreateResponse, error) {
	ret := mock.Called(ctx, service, options)

	var r0 types.ServiceCreateResponse
	if rf, ok := ret.Get(0).(func(context.Context, swarm.ServiceSpec, types.ServiceCreateOptions) types.ServiceCreateResponse); ok {
		r0 = rf(ctx, service, options)
	} else {
		r0 = ret.Get(0).(types.ServiceCreateResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, swarm.ServiceSpec, types.ServiceCreateOptions) error); ok {
		r1 = rf(ctx, service, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ServiceInspectWithRaw(ctx context.Context, serviceID string, options types.ServiceInspectOptions) (swarm.Service, []byte, error) {
	ret := mock.Called(ctx, serviceID, options)

	var r0 swarm.Service
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ServiceInspectOptions) swarm.Service); ok {
		r0 = rf(ctx, serviceID, options)
	} else {
		r0 = ret.Get(0).(swarm.Service)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ServiceInspectOptions) []byte); ok {
		r1 = rf(ctx, serviceID, options)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string, types.ServiceInspectOptions) error); ok {
		r2 = rf(ctx, serviceID, options)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) ServiceList(ctx context.Context, options types.ServiceListOptions) ([]swarm.Service, error) {
	ret := mock.Called(ctx, options)

	var r0 []swarm.Service
	if rf, ok := ret.Get(0).(func(context.Context, types.ServiceListOptions) []swarm.Service); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]swarm.Service)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.ServiceListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ServiceLogs(ctx context.Context, serviceID string, options types.ContainerLogsOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, serviceID, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerLogsOptions) io.ReadCloser); ok {
		r0 = rf(ctx, serviceID, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ContainerLogsOptions) error); ok {
		r1 = rf(ctx, serviceID, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) ServiceRemove(ctx context.Context, serviceID string) error {
	ret := mock.Called(ctx, serviceID)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string) error); ok {
		r0 = rf(ctx, serviceID)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) ServiceUpdate(ctx context.Context, serviceID string, version swarm.Version, service swarm.ServiceSpec, options types.ServiceUpdateOptions) (types.ServiceUpdateResponse, error) {
	ret := mock.Called(ctx, serviceID, version, service, options)

	var r0 types.ServiceUpdateResponse
	if rf, ok := ret.Get(0).(func(context.Context, string, swarm.Version, swarm.ServiceSpec, types.ServiceUpdateOptions) types.ServiceUpdateResponse); ok {
		r0 = rf(ctx, serviceID, version, service, options)
	} else {
		r0 = ret.Get(0).(types.ServiceUpdateResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, swarm.Version, swarm.ServiceSpec, types.ServiceUpdateOptions) error); ok {
		r1 = rf(ctx, serviceID, version, service, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SwarmGetUnlockKey(ctx context.Context) (types.SwarmUnlockKeyResponse, error) {
	ret := mock.Called(ctx)

	var r0 types.SwarmUnlockKeyResponse
	if rf, ok := ret.Get(0).(func(context.Context) types.SwarmUnlockKeyResponse); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(types.SwarmUnlockKeyResponse)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SwarmInit(ctx context.Context, req swarm.InitRequest) (string, error) {
	ret := mock.Called(ctx, req)

	var r0 string
	if rf, ok := ret.Get(0).(func(context.Context, swarm.InitRequest) string); ok {
		r0 = rf(ctx, req)
	} else {
		r0 = ret.Get(0).(string)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, swarm.InitRequest) error); ok {
		r1 = rf(ctx, req)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SwarmInspect(ctx context.Context) (swarm.Swarm, error) {
	ret := mock.Called(ctx)

	var r0 swarm.Swarm
	if rf, ok := ret.Get(0).(func(context.Context) swarm.Swarm); ok {
		r0 = rf(ctx)
	} else {
		r0 = ret.Get(0).(swarm.Swarm)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context) error); ok {
		r1 = rf(ctx)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) SwarmJoin(ctx context.Context, req swarm.JoinRequest) error {
	ret := mock.Called(ctx, req)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, swarm.JoinRequest) error); ok {
		r0 = rf(ctx, req)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) SwarmLeave(ctx context.Context, force bool) error {
	ret := mock.Called(ctx, force)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, bool) error); ok {
		r0 = rf(ctx, force)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) SwarmUnlock(ctx context.Context, req swarm.UnlockRequest) error {
	ret := mock.Called(ctx, req)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, swarm.UnlockRequest) error); ok {
		r0 = rf(ctx, req)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) SwarmUpdate(ctx context.Context, version swarm.Version, _a2 swarm.Spec, flags swarm.UpdateFlags) error {
	ret := mock.Called(ctx, version, _a2, flags)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, swarm.Version, swarm.Spec, swarm.UpdateFlags) error); ok {
		r0 = rf(ctx, version, _a2, flags)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) TaskInspectWithRaw(ctx context.Context, taskID string) (swarm.Task, []byte, error) {
	ret := mock.Called(ctx, taskID)

	var r0 swarm.Task
	if rf, ok := ret.Get(0).(func(context.Context, string) swarm.Task); ok {
		r0 = rf(ctx, taskID)
	} else {
		r0 = ret.Get(0).(swarm.Task)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, taskID)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, taskID)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) TaskList(ctx context.Context, options types.TaskListOptions) ([]swarm.Task, error) {
	ret := mock.Called(ctx, options)

	var r0 []swarm.Task
	if rf, ok := ret.Get(0).(func(context.Context, types.TaskListOptions) []swarm.Task); ok {
		r0 = rf(ctx, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).([]swarm.Task)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, types.TaskListOptions) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) TaskLogs(ctx context.Context, taskID string, options types.ContainerLogsOptions) (io.ReadCloser, error) {
	ret := mock.Called(ctx, taskID, options)

	var r0 io.ReadCloser
	if rf, ok := ret.Get(0).(func(context.Context, string, types.ContainerLogsOptions) io.ReadCloser); ok {
		r0 = rf(ctx, taskID, options)
	} else {
		if ret.Get(0) != nil {
			r0 = ret.Get(0).(io.ReadCloser)
		}
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string, types.ContainerLogsOptions) error); ok {
		r1 = rf(ctx, taskID, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) VolumeCreate(ctx context.Context, options volume.VolumeCreateBody) (types.Volume, error) {
	ret := mock.Called(ctx, options)

	var r0 types.Volume
	if rf, ok := ret.Get(0).(func(context.Context, volume.VolumeCreateBody) types.Volume); ok {
		r0 = rf(ctx, options)
	} else {
		r0 = ret.Get(0).(types.Volume)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, volume.VolumeCreateBody) error); ok {
		r1 = rf(ctx, options)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) VolumeInspect(ctx context.Context, volumeID string) (types.Volume, error) {
	ret := mock.Called(ctx, volumeID)

	var r0 types.Volume
	if rf, ok := ret.Get(0).(func(context.Context, string) types.Volume); ok {
		r0 = rf(ctx, volumeID)
	} else {
		r0 = ret.Get(0).(types.Volume)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, string) error); ok {
		r1 = rf(ctx, volumeID)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) VolumeInspectWithRaw(ctx context.Context, volumeID string) (types.Volume, []byte, error) {
	ret := mock.Called(ctx, volumeID)

	var r0 types.Volume
	if rf, ok := ret.Get(0).(func(context.Context, string) types.Volume); ok {
		r0 = rf(ctx, volumeID)
	} else {
		r0 = ret.Get(0).(types.Volume)
	}

	var r1 []byte
	if rf, ok := ret.Get(1).(func(context.Context, string) []byte); ok {
		r1 = rf(ctx, volumeID)
	} else {
		if ret.Get(1) != nil {
			r1 = ret.Get(1).([]byte)
		}
	}

	var r2 error
	if rf, ok := ret.Get(2).(func(context.Context, string) error); ok {
		r2 = rf(ctx, volumeID)
	} else {
		r2 = ret.Error(2)
	}

	return r0, r1, r2
}

func (mock *MockClient) VolumeList(ctx context.Context, filter filters.Args) (volume.VolumeListOKBody, error) {
	ret := mock.Called(ctx, filter)

	var r0 volume.VolumeListOKBody
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) volume.VolumeListOKBody); ok {
		r0 = rf(ctx, filter)
	} else {
		r0 = ret.Get(0).(volume.VolumeListOKBody)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, filter)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}

func (mock *MockClient) VolumeRemove(ctx context.Context, volumeID string, force bool) error {
	ret := mock.Called(ctx, volumeID, force)

	var r0 error
	if rf, ok := ret.Get(0).(func(context.Context, string, bool) error); ok {
		r0 = rf(ctx, volumeID, force)
	} else {
		r0 = ret.Error(0)
	}

	return r0
}

func (mock *MockClient) VolumesPrune(ctx context.Context, pruneFilter filters.Args) (types.VolumesPruneReport, error) {
	ret := mock.Called(ctx, pruneFilter)

	var r0 types.VolumesPruneReport
	if rf, ok := ret.Get(0).(func(context.Context, filters.Args) types.VolumesPruneReport); ok {
		r0 = rf(ctx, pruneFilter)
	} else {
		r0 = ret.Get(0).(types.VolumesPruneReport)
	}

	var r1 error
	if rf, ok := ret.Get(1).(func(context.Context, filters.Args) error); ok {
		r1 = rf(ctx, pruneFilter)
	} else {
		r1 = ret.Error(1)
	}

	return r0, r1
}
