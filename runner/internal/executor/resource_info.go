package executor

import (
	"bytes"
	"context"
	"math/bits"
	"regexp"
	"strconv"
	"strings"

	"github.com/sirupsen/logrus"
	"gitlab.com/dstackai/dstackai-runner/consts"
	"gitlab.com/dstackai/dstackai-runner/internal/container"
	"gitlab.com/dstackai/dstackai-runner/internal/gerrors"
	"gitlab.com/dstackai/dstackai-runner/internal/log"
	"gitlab.com/dstackai/dstackai-runner/internal/models"
)

func updateResourceInfo() (*models.Resource, error) {
	ctx := context.Background()

	resources := new(models.Resource)
	engine := container.NewEngine()
	resources.Cpus, resources.MemoryMiB = engine.CPU(), engine.MemMiB()
	if engine.DockerRuntime() == consts.NVIDIA_RUNTIME {
		var logger bytes.Buffer
		docker, err := engine.Create(ctx,
			&container.Spec{
				Image:    consts.NVIDIA_CUDA_IMAGE,
				Commands: strings.Split(consts.NVIDIA_SMI_CMD, " "),
			},
			&logger)
		if err != nil {
			log.Error(ctx, "Failed to create docker container", "err", err)
			return nil, gerrors.Wrap(err)
		}
		err = docker.Run(ctx)
		if err != nil {
			if strings.Contains(err.Error(), consts.NVIDIA_DRIVER_INIT_ERROR) {
				return nil, nil
			}
			return nil, gerrors.Wrap(err)
		}
		if err = docker.Wait(ctx); err != nil {
			log.Error(ctx, "Failed to create docker container", "err", err)
			return nil, gerrors.Wrap(err)
		}

		output := strings.Split(strings.TrimRight(logger.String(), "\n"), "\n")
		logrus.Infof("Docker container output %s", output)

		var gpus []models.Gpu
		for _, x := range output {
			regex := regexp.MustCompile(` *, *`)
			gpu := regex.Split(x, -1)
			memoryTotal := strings.Trim(strings.Split(gpu[1], "MiB")[0], " ")
			memoryMiB, err := strconv.ParseInt(memoryTotal, 10, bits.UintSize)
			if err != nil {
				return nil, gerrors.Newf("GPU memory conversion to integer failed: %v", err)
			}
			gpus = append(gpus, models.Gpu{
				Name:      gpu[0],
				MemoryMiB: uint64(memoryMiB),
			})
		}
		resources.Gpus = gpus
	}
	return resources, nil
}
