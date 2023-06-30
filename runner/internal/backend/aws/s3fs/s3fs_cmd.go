package s3fs

import (
	"context"
	"errors"
	"fmt"
	"github.com/dstackai/dstack/runner/internal/backend/base"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"strings"

	"github.com/docker/docker/api/types/mount"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

var _ base.Artifacter = (*S3FSCmd)(nil)

type S3FSCmd struct {
	bucket     string
	workDir    string
	pathLocal  string
	pathRemote string

	cmd *exec.Cmd

	storage *Copier
}

func (s *S3FSCmd) BeforeRun(ctx context.Context) error {
	log.Debug(ctx, "BeforeRun")
	err := s.storage.CreateDirObject(ctx, s.bucket, s.pathRemote)
	if err != nil {
		return err
	}

	s.cmd.Stdout = os.Stdout
	s.cmd.Stderr = os.Stderr

	s.cmd.Args = append(s.cmd.Args, fmt.Sprintf("%s:/%s", s.bucket, s.pathRemote), path.Join(s.workDir, s.pathLocal))
	err = s.cmd.Start()
	if err != nil {
		return gerrors.Wrap(err)
	}

	return nil

}

func (s *S3FSCmd) AfterRun(ctx context.Context) error {
	log.Debug(ctx, "AfterRun", "mounts_cnt", 1)
	var oneOf error
	if s.cmd.Process != nil {
		err := s.cmd.Process.Signal(os.Interrupt)
		if err != nil {
			log.Error(ctx, "s3fsCmd send signal fail", "err", err, "dir", s.cmd.Args[len(s.cmd.Args)-1])
			oneOf = err
		}
	}
	err := s.cmd.Wait()
	if err != nil {
		log.Error(ctx, "s3fsCmd Wait fail", "err", err, "dir", s.cmd.Args[len(s.cmd.Args)-1])
		oneOf = err
	}
	return oneOf
}

func (s *S3FSCmd) DockerBindings(workDir string) ([]mount.Mount, error) {
	cleanPath := filepath.Clean(s.pathLocal)
	if path.IsAbs(cleanPath) && path.Dir(cleanPath) == cleanPath {
		return nil, errors.New("directory needs to be a non-root path")
	}
	dir := s.pathLocal
	if !filepath.IsAbs(s.pathLocal) {
		dir = path.Join(workDir, s.pathLocal)
	}

	return []mount.Mount{
		{
			Type:   mount.TypeBind,
			Source: path.Join(s.workDir, s.pathLocal),
			Target: dir,
		},
	}, nil
}

/*
func mapLogrusS3FS(level logrus.Level) string {
	switch level {
	case logrus.ErrorLevel:
		return "err"
	case logrus.WarnLevel:
		return "warn"
	case logrus.InfoLevel:
		return "info"
	}
	if level >= logrus.DebugLevel {
		return "debug"
	}
	return "crit"
}
*/

func New(ctx context.Context, bucket, region, IAMRole, workDir, localPath, remotePath string) (*S3FSCmd, error) {
	log.Trace(ctx, "Build FUSE engine")
	//logger := log.GetLogger(ctx)
	cmd := exec.Command("s3fs", "-f",
		"-o", "endpoint="+region,
		//"-o", "dbglevel="+mapLogrusS3FS(6),
		"-o", "dbglevel=warn",
		"-o", "nonempty",
		"-o", "iam_role="+IAMRole,
	)
	if os.Getuid() != 0 {
		cmd.Args = append(cmd.Args, "-o", "allow_root")
	}

	dir := path.Join(workDir, localPath)
	err := os.MkdirAll(dir, 0o755)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}

	s := &S3FSCmd{
		bucket:     bucket,
		workDir:    workDir,
		pathLocal:  localPath,
		pathRemote: remotePath,
		cmd:        cmd,
		storage:    NewCopier(region),
	}
	err = s.Validate(ctx)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	log.Trace(context.Background(), "End build s#")
	return s, nil
}
func (s *S3FSCmd) Validate(ctx context.Context) error {
	var final error
	cmd := exec.Command("s3fs", "--version")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	err := cmd.Run()
	if err != nil {
		final = err
		log.Error(ctx, "s3fs binary is required to enable FUSE artifact handling")
		log.Error(ctx, "sudo apt/yum install s3fs")
	}
	err = validateAllowOther(ctx)
	if err != nil {
		final = err
	}

	return final

}

func validateAllowOther(ctx context.Context) error {
	if 0 == os.Getuid() {
		return nil
	}
	buf, err := os.ReadFile("/etc/fuse.conf")
	if err != nil {
		return err
	}
	for _, line := range strings.Split(string(buf), "\n") {
		line = strings.Split(line, "#")[0]
		line = strings.TrimSpace(line)
		if line == "user_allow_other" {
			return nil
		}
	}
	log.Error(ctx, "to run dstack as non-root it is required to uncomment user_allow_other option in /etc/fuse.conf")
	return gerrors.New("user_allow_other required in /etc/fuse.conf")
}
