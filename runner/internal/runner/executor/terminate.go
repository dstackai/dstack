package executor

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	"golang.org/x/sys/unix"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

// sessionPollInterval is how often the job's session is re-examined while waiting for it to
// empty out between termination stages.
const sessionPollInterval = 100 * time.Millisecond

// terminateSession stops whatever is left of the job, in stages.
//
// The job has already been interrupted through the terminal by interruptJob, which the line
// discipline delivers to the terminal's foreground process group alone. Anything the job moved
// elsewhere -- a `cmd &` job, which job control puts in a process group of its own -- never
// sees that interrupt, and neither does the SIGHUP the kernel sends to the foreground group
// when the session leader exits.
func (ex *RunExecutor) terminateSession(ctx context.Context, sid int) {
	if ex.waitForSessionExit(sid, ex.hupDelay) {
		return
	}
	if pids := hangUpSession(sid); len(pids) > 0 {
		log.Warning(ctx, "Processes still running after the interrupt, sent SIGHUP", "pids", pids)
	}

	if ex.waitForSessionExit(sid, ex.killDelay-ex.hupDelay) {
		return
	}
	if pids := signalSession(sid, unix.SIGKILL); len(pids) > 0 {
		log.Error(ctx, "Processes still running after SIGHUP, sent SIGKILL", "pids", pids)
	}
}

// waitForSessionExit reports whether the session emptied out within d.
func (ex *RunExecutor) waitForSessionExit(sid int, d time.Duration) bool {
	deadline := time.Now().Add(d)
	for {
		if len(sessionPids(sid)) == 0 {
			return true
		}
		if !time.Now().Before(deadline) {
			return false
		}
		time.Sleep(sessionPollInterval)
	}
}

// hangUpSession tells everything still running in session sid that its terminal is going away.
//
// SIGHUP is what a terminal hangup delivers, and an idle shell exits on it. SIGCONT follows
// because a stopped process would not act on the SIGHUP until something resumes it -- SIGKILL
// and SIGCONT are the only signals that reach a stopped process.
func hangUpSession(sid int) []int {
	pids := signalSession(sid, unix.SIGHUP)
	signalSession(sid, unix.SIGCONT)
	return pids
}

// signalSession sends sig to every live process in session sid, and reports which ones it
// reached. The wrapper shell is one of them, and so is anything the job backgrounded -- which
// never saw the interrupt at all, rather than having declined to act on it.
//
// The processes are enumerated rather than signalled as a group: under job control the job does
// not share the shell's process group, so there is no one group to signal, and kill(2) has no
// session-wide form. A session is the right scope because a child inherits its parent's session
// id, and only setsid() changes it.
func signalSession(sid int, sig unix.Signal) []int {
	pids := sessionPids(sid)
	signalled := make([]int, 0, len(pids))
	for _, pid := range pids {
		if err := unix.Kill(pid, sig); err == nil {
			signalled = append(signalled, pid)
		}
	}
	return signalled
}

// sessionPids returns the live processes in session sid. Zombies are left out: they have
// already exited and only await reaping, so counting them would keep the session looking busy
// forever.
func sessionPids(sid int) []int {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil
	}
	self := os.Getpid()
	var pids []int
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil || pid == self || pid == 1 {
			continue
		}
		if procSid, err := unix.Getsid(pid); err != nil || procSid != sid {
			continue
		}
		if state, ok := procState(pid); !ok || state == 'Z' {
			continue
		}
		pids = append(pids, pid)
	}
	return pids
}

// procState returns the process state character from /proc/<pid>/stat.
func procState(pid int) (byte, bool) {
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if err != nil {
		return 0, false
	}
	// The command name field is parenthesized and may itself contain spaces and parentheses,
	// so the state is the first field after the last ')'.
	end := bytes.LastIndexByte(data, ')')
	if end < 0 || end+2 >= len(data) {
		return 0, false
	}
	return data[end+2], true
}
