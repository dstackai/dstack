package ports

import (
	"context"
	"fmt"
	"github.com/docker/go-connections/nat"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
	"strconv"
)

func GetAppsExposedPorts(ctx context.Context, apps []models.App, isLocalBackend bool) nat.PortSet {
	resp := make(nat.PortSet)
	for _, app := range apps {
		if app.Name == "openssh-server" && isLocalBackend {
			log.Trace(ctx, "Expose only OpenSSH server", "Port", app.Port)
			return nat.PortSet{
				nat.Port(fmt.Sprintf("%d/tcp", app.Port)): struct{}{},
			}
		}
		resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = struct{}{}
	}
	return resp
}

func GetAppsBindingPorts(ctx context.Context, apps []models.App, doMapping bool) (nat.PortMap, error) {
	resp := make(nat.PortMap)
	if doMapping { // no host mode
		for i, app := range apps {
			if app.Name == "openssh-server" { // ports will be forwarded through container's ssh server
				mapToPort := app.MapToPort
				if mapToPort > 0 {
					if free, _ := CheckPort(mapToPort); !free {
						return nat.PortMap{}, fmt.Errorf("port %d is in use", app.MapToPort)
					}
				} else {
					mapToPort = app.Port
					for {
						if free, _ := CheckPort(mapToPort); free {
							break
						}
						mapToPort += 1
					}
					apps[i].MapToPort = mapToPort
				}
				resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = []nat.PortBinding{
					{
						HostIP:   "0.0.0.0",
						HostPort: strconv.Itoa(mapToPort),
					},
				}
				log.Trace(ctx, "Bind only OpenSSH server", "HostPort", mapToPort)
				return resp, nil
			}
		}
	}
	// do identity mapping
	if !doMapping {
		for _, app := range apps {
			resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = []nat.PortBinding{
				{
					HostIP:   "0.0.0.0",
					HostPort: strconv.Itoa(app.Port),
				},
			}
		}
		log.Trace(ctx, "Identity port mapping", "AppsBindingPorts", resp)
		return resp, nil
	}
	// do dynamic mapping
	usedPorts := make(map[int]bool)
	for _, app := range apps { // user-defined mapping
		if app.MapToPort == 0 {
			continue
		}
		free, _ := CheckPort(app.MapToPort)
		if !free {
			return nat.PortMap{}, fmt.Errorf("port %d is in use", app.MapToPort)
		}
		usedPorts[app.MapToPort] = true
		resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: strconv.Itoa(app.MapToPort),
			},
		}
	}
	for i, app := range apps { // get the closest free port
		if app.MapToPort > 0 {
			continue
		}
		mapToPort := app.Port
		for {
			if _, used := usedPorts[mapToPort]; !used {
				free, _ := CheckPort(mapToPort)
				if free {
					break
				}
			}
			mapToPort += 1
		}
		apps[i].MapToPort = mapToPort // for fix_url
		usedPorts[mapToPort] = true
		resp[nat.Port(fmt.Sprintf("%d/tcp", app.Port))] = []nat.PortBinding{
			{
				HostIP:   "0.0.0.0",
				HostPort: strconv.Itoa(mapToPort),
			},
		}
	}
	log.Trace(ctx, "Dynamic port mapping", "AppsBindingPorts", resp)
	return resp, nil
}
