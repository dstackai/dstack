package host

import (
	"context"
	"fmt"
	"net"
	"runtime"

	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/shirou/gopsutil/v4/mem"
	"golang.org/x/sys/unix"
)

func GetCpuCount(ctx context.Context) int {
	return runtime.NumCPU()
}

// GetTotalMemory returns total amount of RAM on this system
func GetTotalMemory(ctx context.Context) (uint64, error) {
	v, err := mem.VirtualMemory()
	if err != nil {
		return 0, fmt.Errorf("cannot get total memory: %w", err)
	}
	return v.Total, nil
}

func GetDiskSize(ctx context.Context, path string) (uint64, error) {
	var stat unix.Statfs_t
	err := unix.Statfs(path, &stat)
	if err != nil {
		return 0, fmt.Errorf("cannot get disk size: %w", err)
	}
	size := stat.Bavail * uint64(stat.Bsize)
	return size, nil
}

func GetNetworkAddresses(ctx context.Context) ([]string, error) {
	var addresses []string
	ifaces, err := net.Interfaces()
	if err != nil {
		return addresses, fmt.Errorf("cannot get interfaces: %w", err)
	}
	for _, iface := range ifaces {
		addrs, err := iface.Addrs()
		if err != nil {
			log.Error(ctx, "cannot get addrs", "iface", iface, "err", err)
			continue
		}
		for _, addr := range addrs {
			switch v := addr.(type) {
			case *net.IPNet:
				if v.IP.IsLoopback() {
					continue
				}
				addresses = append(addresses, addr.String())
			}
		}
	}
	return addresses, nil
}
