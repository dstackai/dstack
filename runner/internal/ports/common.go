package ports

import (
	"context"
	"golang.org/x/sys/unix"
	"net"
	"runtime"
	"strconv"
	"syscall"
)

func GetFreePort() (int, error) {
	addr, err := net.ResolveTCPAddr("tcp", "localhost:0")
	if err != nil {
		return 0, err
	}

	l, err := net.ListenTCP("tcp", addr)
	if err != nil {
		return 0, err
	}
	defer func() {
		_ = l.Close()
	}()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func CheckPort(port int) (bool, error) {
	host := ":" + strconv.Itoa(port)
	// force IPv4 to detect used ports
	// https://stackoverflow.com/a/51073906
	config := &net.ListenConfig{Control: reusePortControl}
	server, err := config.Listen(context.TODO(), "tcp4", host)
	if err != nil {
		return false, err
	}
	_ = server.Close()
	return true, nil
}

func reusePortControl(network, address string, conn syscall.RawConn) error {
	if runtime.GOOS == "windows" {
		return nil
	}
	return conn.Control(func(descriptor uintptr) {
		_ = unix.SetsockoptInt(int(descriptor), unix.SOL_SOCKET, unix.SO_REUSEPORT, 1)
	})
}
