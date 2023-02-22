module github.com/dstackai/dstack/runner

go 1.16

require (
	github.com/aws/aws-sdk-go v1.38.7
	github.com/aws/aws-sdk-go-v2 v1.16.14
	github.com/aws/aws-sdk-go-v2/config v1.10.1
	github.com/aws/aws-sdk-go-v2/feature/s3/manager v1.7.1
	github.com/aws/aws-sdk-go-v2/service/s3 v1.19.0
	github.com/aws/smithy-go v1.13.2
	github.com/bluekeyes/go-gitdiff v0.6.0
	github.com/docker/docker v20.10.6+incompatible
	github.com/docker/go-connections v0.4.0
	github.com/go-git/go-git/v5 v5.4.2
	github.com/google/uuid v1.3.0
	github.com/sirupsen/logrus v1.8.1
	github.com/stretchr/testify v1.8.1
	github.com/urfave/cli/v2 v2.3.0
	go.uber.org/atomic v1.4.0
	golang.org/x/crypto v0.6.0
	gopkg.in/yaml.v2 v2.4.0
)

require (
	cloud.google.com/go/compute v1.14.0
	cloud.google.com/go/logging v1.6.1
	cloud.google.com/go/secretmanager v1.10.0
	cloud.google.com/go/storage v1.29.0
	github.com/aws/aws-sdk-go-v2/feature/ec2/imds v1.12.15
	github.com/aws/aws-sdk-go-v2/internal/configsources v1.1.21 // indirect
	github.com/aws/aws-sdk-go-v2/internal/endpoints/v2 v2.4.15 // indirect
	github.com/aws/aws-sdk-go-v2/service/cloudwatchlogs v1.15.7
	github.com/aws/aws-sdk-go-v2/service/ec2 v1.53.0
	github.com/aws/aws-sdk-go-v2/service/secretsmanager v1.15.18
	github.com/containerd/containerd v1.5.2 // indirect
	github.com/gorilla/mux v1.8.0 // indirect
	github.com/gorilla/websocket v1.5.0
	github.com/moby/term v0.0.0-20201216013528-df9cb8a40635 // indirect
	github.com/morikuni/aec v1.0.0 // indirect
	github.com/opencontainers/image-spec v1.0.1
	google.golang.org/api v0.106.0
	gopkg.in/yaml.v3 v3.0.1
	modernc.org/sqlite v1.20.3
)

replace github.com/kahing/goofys => github.com/dstackai/goofys v0.24.1-0.20211210032445-aae1cc43d188
