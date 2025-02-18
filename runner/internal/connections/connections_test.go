package connections

import (
	"io/fs"
	"os"
	"testing"
	"time"

	"github.com/prometheus/procfs"
	"github.com/stretchr/testify/assert"
)

func TestConnectionTracker(t *testing.T) {
	procfsDir := t.TempDir()
	proc, err := procfs.NewFS(procfsDir)
	assert.NoError(t, err)
	err = os.Mkdir(procfsDir+"/net", os.ModePerm)
	assert.NoError(t, err)
	tracker := NewConnectionTracker(ConnectionTrackerConfig{
		Port:            4096,
		MinConnDuration: 5 * time.Second,
		Procfs:          proc,
	})
	ticker := make(chan time.Time)
	// Open sockets on ports 53 and 4096 + established connection to port 53 (irrelevant)
	noConnTcp := `  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 3500007F:0035 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
   1: 00000000:1000 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
   2: 3500007F:0035 0100007F:1234 01 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
`
	noConnTcp6 := `  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000000000000:0035 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
   1: 00000000000000000000000000000000:1000 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
   2: 00000000000000000000000000000000:0035 00000000000000000000000001000000:1234 01 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0
`
	// Established connection to port 4096 (relevant)
	connTcp := "   3: 00000000:1000 0100007F:4321 01 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0"
	connTcp6 := "   3: 00000000000000000000000000000000:1000 00000000000000000000000001000000:4321 01 00000000:00000000 00:00000000 00000000     0        0 12345 1 0000000000000000 100 0 0 10 0"

	// Tracking did not start yet
	// Returns 0 secs
	assert.Equal(t, int64(0), tracker.GetNoConnectionsSecs())

	go tracker.Track(ticker)
	defer tracker.Stop()
	assert.Equal(t, int64(0), tracker.GetNoConnectionsSecs())

	// There is a 2-second-old connection
	// Returns 2 secs (the connection doesn't count as it's < MinConnDuration)
	writeProcfs(t, procfsDir, noConnTcp+connTcp, noConnTcp6)
	tick := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	ticker <- tick
	wait()
	tick = tick.Add(2 * time.Second)
	ticker <- tick
	wait()
	assert.Equal(t, int64(2), tracker.GetNoConnectionsSecs())

	// There is a 6-second-old connection
	// Returns 0 secs (the connection is >= MinConnDuration)
	tick = tick.Add(4 * time.Second)
	ticker <- tick
	wait()
	assert.Equal(t, int64(0), tracker.GetNoConnectionsSecs())

	// The connection is closed and there are no connections for 15 secs.
	// Returns 15 secs
	writeProcfs(t, procfsDir, noConnTcp, noConnTcp6)
	tick = tick.Add(15 * time.Second)
	ticker <- tick
	wait()
	assert.Equal(t, int64(15), tracker.GetNoConnectionsSecs())

	// There is a 7-second-old connection over IPv6
	// Returns 0 secs (the connection is >= MinConnDuration)
	writeProcfs(t, procfsDir, noConnTcp, noConnTcp6+connTcp6)
	tick = tick.Add(1 * time.Second)
	ticker <- tick
	tick = tick.Add(7 * time.Second)
	ticker <- tick
	wait()
	assert.Equal(t, int64(0), tracker.GetNoConnectionsSecs())
}

func writeProcfs(t *testing.T, procfsDir, tcp, tcp6 string) {
	err := os.WriteFile(procfsDir+"/net/tcp", []byte(tcp), fs.ModePerm)
	assert.NoError(t, err)
	err = os.WriteFile(procfsDir+"/net/tcp6", []byte(tcp6), fs.ModePerm)
	assert.NoError(t, err)
}

func wait() {
	time.Sleep(30 * time.Millisecond)
}
