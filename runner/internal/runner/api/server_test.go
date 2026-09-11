package api

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/require"

	"github.com/dstackai/dstack/runner/internal/common/types"
	"github.com/dstackai/dstack/runner/internal/runner/executor"
	"github.com/dstackai/dstack/runner/internal/runner/schemas"
)

// fakeExecutor implements executor.Executor with the minimum needed to drive the handlers.
type fakeExecutor struct {
	mu    sync.RWMutex
	state string
}

func (e *fakeExecutor) SetJob(schemas.SubmitBody)                {}
func (e *fakeExecutor) WriteFileArchive(string, io.Reader) error { return nil }
func (e *fakeExecutor) WriteRepoBlob(io.Reader) error            { return nil }
func (e *fakeExecutor) Setup(context.Context) error              { return nil }
func (e *fakeExecutor) JobInfo() (string, string)                { return "", "" }
func (e *fakeExecutor) Run(context.Context) error                { return nil }
func (e *fakeExecutor) Finalize(context.Context)                 {}

func (e *fakeExecutor) GetHistory(int64) *schemas.PullResponse  { return &schemas.PullResponse{} }
func (e *fakeExecutor) GetJobWsLogsHistory() []schemas.LogEvent { return nil }

func (e *fakeExecutor) GetRunnerState() string      { return e.state }
func (e *fakeExecutor) SetRunnerState(state string) { e.state = state }

func (e *fakeExecutor) SetJobState(context.Context, schemas.JobState) {}
func (e *fakeExecutor) SetJobStateWithTerminationReason(
	context.Context, schemas.JobState, types.TerminationReason, string,
) {
}

func (e *fakeExecutor) Lock()    { e.mu.Lock() }
func (e *fakeExecutor) Unlock()  { e.mu.Unlock() }
func (e *fakeExecutor) RLock()   { e.mu.RLock() }
func (e *fakeExecutor) RUnlock() { e.mu.RUnlock() }

func newTestServer(t *testing.T, state string) *Server {
	t.Helper()
	s, err := NewServer(t.Context(), "localhost:0", "test", &fakeExecutor{state: state})
	require.NoError(t, err)
	return s
}

func pull(t *testing.T, s *Server) {
	t.Helper()
	_, err := s.pullGetHandler(
		httptest.NewRecorder(),
		httptest.NewRequest(http.MethodGet, "/api/pull", nil),
	)
	require.NoError(t, err)
}

// The runner enters WaitLogsFinished as soon as the job is asked to stop, but keeps serving
// until the executor returns, which never happens while the job holds the pty open. The dstack
// server goes on polling, so several pulls observe the state.
func TestPullGetHandler_RepeatedFinalPulls(t *testing.T) {
	s := newTestServer(t, executor.WaitLogsFinished)

	for range 3 {
		pull(t, s)
	}

	select {
	case <-s.pullDoneCh:
	default:
		t.Fatal("pullDoneCh must be closed after a pull in the WaitLogsFinished state")
	}
}

// The handler takes only a read lock, so pulls can observe the state concurrently.
func TestPullGetHandler_ConcurrentFinalPulls(t *testing.T) {
	s := newTestServer(t, executor.WaitLogsFinished)

	var wg sync.WaitGroup
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			pull(t, s)
		}()
	}
	wg.Wait()

	select {
	case <-s.pullDoneCh:
	default:
		t.Fatal("pullDoneCh must be closed after a pull in the WaitLogsFinished state")
	}
}

func TestPullGetHandler_NotFinishedKeepsPullDoneOpen(t *testing.T) {
	s := newTestServer(t, executor.ServeLogs)

	pull(t, s)

	select {
	case <-s.pullDoneCh:
		t.Fatal("pullDoneCh must stay open while the executor still serves logs")
	default:
	}
}

// Nothing limits the number of concurrent /logs_ws connections, and each is drained by its
// own goroutine.
func TestCloseWsDone_Idempotent(t *testing.T) {
	s := newTestServer(t, executor.WaitLogsFinished)

	var wg sync.WaitGroup
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.closeWsDone()
		}()
	}
	wg.Wait()

	select {
	case <-s.wsDoneCh:
	default:
		t.Fatal("wsDoneCh must be closed")
	}
}

// Two attached clients -- `dstack apply` in one terminal and `dstack attach` in another --
// each open their own /logs_ws stream. Both drain, both see shutdownCh, and both reach the
// close. Unlike the /api/pull handler, streamJobLogs runs in a bare goroutine, so an
// unrecovered panic there takes down the whole runner.
func TestLogsWs_TwoClientsBothDrain(t *testing.T) {
	s := newTestServer(t, executor.ServeLogs)
	httpSrv := httptest.NewServer(s.srv.Handler)
	defer httpSrv.Close()

	wsURL := "ws" + strings.TrimPrefix(httpSrv.URL, "http") + "/logs_ws"
	for range 2 {
		conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
		require.NoError(t, err)
		defer func() { _ = conn.Close() }()
	}

	// Let both streams reach the drained-and-sleeping branch of their loop.
	time.Sleep(300 * time.Millisecond)
	close(s.shutdownCh)

	select {
	case <-s.wsDoneCh:
	case <-time.After(5 * time.Second):
		t.Fatal("wsDoneCh must be closed once a stream has drained after shutdown")
	}
	// Give the second stream time to reach its own close.
	time.Sleep(500 * time.Millisecond)
}

// /api/stop must not turn the next pull into the final one. The job is still stopping -- the
// runner has up to killDelay before the command is killed -- and the state it will report does
// not exist yet. Treating that pull as final lets the runner exit before handing the state
// over, and the server ends the job as unreachable instead.
func TestStop_DoesNotMarkLogsFinished(t *testing.T) {
	s := newTestServer(t, executor.ServeLogs)
	s.cancelRun = func() {} // set by runPostHandler in production

	_, err := s.stopPostHandler(
		httptest.NewRecorder(),
		httptest.NewRequest(http.MethodPost, "/api/stop", nil),
	)
	require.NoError(t, err)
	pull(t, s)

	select {
	case <-s.pullDoneCh:
		t.Fatal("pullDoneCh must stay open while the job is still stopping")
	default:
	}

	// The executor finishes and records the terminal job state.
	s.executor.Lock()
	s.executor.SetRunnerState(executor.WaitLogsFinished)
	s.executor.Unlock()
	pull(t, s)

	select {
	case <-s.pullDoneCh:
	default:
		t.Fatal("the first pull after the executor finished must be the final one")
	}
}
