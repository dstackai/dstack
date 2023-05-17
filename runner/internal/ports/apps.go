package ports

import (
	"fmt"
	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/internal/models"
	"strconv"
)

func GetAppsExposedPorts(apps []models.App) nat.PortSet {
	resp := make(nat.PortSet)
	for _, app := range apps {
		resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = struct{}{}
	}
	return resp
}

func GetAppsBindingPorts(apps []models.App) nat.PortMap {
	resp := make(nat.PortMap)
	for _, app := range apps {
		resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: strconv.Itoa(app.Port),
			},
		}
	}
	return resp
}
