package log

import (
	"context"
	"fmt"
	"io"
	"os"

	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/sirupsen/logrus"
)

type loggerKey struct{}

func NewEntry(out io.Writer, level int) *logrus.Entry {
	return logrus.NewEntry(&logrus.Logger{
		Out: out,
		Formatter: &logrus.TextFormatter{
			DisableQuote:    true,
			FullTimestamp:   true,
			DisableSorting:  true,
			TimestampFormat: "2006-01-02T15:04:05.999999Z07:00",
		},
		Hooks: make(logrus.LevelHooks),
		Level: logrus.Level(level),
	})
}

var DefaultEntry = NewEntry(os.Stderr, int(logrus.InfoLevel))

func Fatal(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Fatal(msg)
}

func Error(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Error(msg)
}

func Warning(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Warning(msg)
}

func Info(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Info(msg)
}

func Debug(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Debug(msg)
}

func Trace(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Trace(msg)
}

func AppendArgsCtx(ctx context.Context, args ...interface{}) context.Context {
	logger := GetLogger(ctx)
	logger = AppendArgs(logger, args...)
	return WithLogger(ctx, logger)
}

func AppendArgs(logger *logrus.Entry, args ...interface{}) *logrus.Entry {
	if len(args) == 0 {
		return logger
	}
	if len(args)%2 != 0 {
		logger.WithField("count", len(args)).Warning("count of log arguments must be odd")
	}
	fields := make(logrus.Fields)
	for idx := 0; idx+1 < len(args); idx += 2 {
		if key, ok := args[idx].(string); ok {
			fields[key] = args[idx+1]
		} else {
			logger.WithFields(logrus.Fields{"idx": idx, "key_type": fmt.Sprintf("%T", args[idx])}).
				Warning("argument for key must be string")
		}
	}
	return logger.WithFields(fields)
}

// https://github.com/containerd/containerd/blob/22beecb7d9bd06e743be9da7e519976417755466/log/context.go

// WithLogger returns a new context with the provided logger. Use in
// combination with logger.WithField(s) for great effect.
func WithLogger(ctx context.Context, logger *logrus.Entry) context.Context {
	e := logger.WithContext(ctx)
	return context.WithValue(ctx, loggerKey{}, e)
}

// GetLogger retrieves the current logger from the context. If no logger is
// available, the default logger is returned.
func GetLogger(ctx context.Context) *logrus.Entry {
	logger := ctx.Value(loggerKey{})

	if logger == nil {
		return DefaultEntry.WithContext(ctx)
	}

	return logger.(*logrus.Entry)
}

func CreateAppendFile(path string) (*os.File, error) {
	f, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE|os.O_APPEND, 0o644)
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	return f, nil
}
