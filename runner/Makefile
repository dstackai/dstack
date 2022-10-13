local:
	GOARCH=amd64 GOOS=windows go build -ldflags "-X 'gitlab.com/dstackai/dstackai-runner/version.Version=$CI_PIPELINE_IID' -X 'gitlab.com/dstackai/dstackai-runner/pkg/log.CloudLogFlag=true' -extldflags '-static'" -o dstack-runner-windows-amd64.exe
	GOARCH=amd64 GOOS=linux go build -ldflags "-X 'gitlab.com/dstackai/dstackai-runner/version.Version=$CI_PIPELINE_IID' -X 'gitlab.com/dstackai/dstackai-runner/pkg/log.CloudLogFlag=true' -extldflags '-static'" -o dstack-runner-linux-amd64
	GOARCH=amd64 GOOS=darwin go build -ldflags "-X 'gitlab.com/dstackai/dstackai-runner/version.Version=$CI_PIPELINE_IID' -X 'gitlab.com/dstackai/dstackai-runner/pkg/log.CloudLogFlag=true' -extldflags '-static'" -o dstack-runner-darwin-amd64
	GOARCH=arm64 GOOS=darwin go build -ldflags "-X 'gitlab.com/dstackai/dstackai-runner/version.Version=$CI_PIPELINE_IID' -X 'gitlab.com/dstackai/dstackai-runner/pkg/log.CloudLogFlag=true' -extldflags '-static'" -o dstack-runner-darwin-arm64
