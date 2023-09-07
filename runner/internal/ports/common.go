package ports

import (
	"github.com/libp2p/go-reuseport"
	"strconv"
)

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
