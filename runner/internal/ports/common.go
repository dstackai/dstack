package ports

import (
	"github.com/libp2p/go-reuseport"
	"net"
	"strconv"
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
	server, err := reuseport.Listen("tcp4", host)
	if err != nil {
		return false, err
	}
	_ = server.Close()
	return true, nil
}
