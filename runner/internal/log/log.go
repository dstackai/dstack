package log

import (
	"context"
	"fmt"
	"io"
	"strings"
	"sync"

	"github.com/sirupsen/logrus"
)

type loggerKey struct{}

var L = logrus.NewEntry(logrus.StandardLogger())

var CloudLog = "true"

var cloud io.Writer
var cloudBuffer []string
var cloudMu sync.Mutex

func init() {
	cloudMu = sync.Mutex{}
	cloudBuffer = make([]string, 0)
	L.Logger.SetFormatter(&logrus.TextFormatter{
		DisableQuote:    true,
		FullTimestamp:   true,
		DisableSorting:  true,
		TimestampFormat: "2006-01-02T15:04:05.999999Z07:00",
	})
}

func Error(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Error(msg)
	if L.Logger.Level >= logrus.ErrorLevel {
		writeCloud("[ERROR]", msg, args)
	}
}

func Warning(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Warning(msg)
	if L.Logger.Level >= logrus.WarnLevel {
		writeCloud("[WARNING]", msg, args)
	}
}

func Info(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Info(msg)
	if L.Logger.Level >= logrus.InfoLevel {
		writeCloud("[INFO]", msg, args)
	}
}

func Debug(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Debug(msg)
	if L.Logger.Level >= logrus.DebugLevel {
		writeCloud("[DEBUG]", msg, args)
	}
}

func Trace(ctx context.Context, msg string, args ...interface{}) {
	logger := AppendArgs(GetLogger(ctx), args...)
	logger.Trace(msg)
	if L.Logger.Level >= logrus.TraceLevel {
		writeCloud("[TRACE]", msg, args)
	}
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
		return L.WithContext(ctx)
	}

	return logger.(*logrus.Entry)
}

func SetCloudLogger(l io.Writer) {
	if CloudLog == "true" {
		cloud = l
	}
}

func writeCloud(level, msg string, args ...interface{}) {
	bld := strings.Builder{}
	bld.WriteString(level)
	bld.WriteRune(':')
	bld.WriteString(msg)
	for _, arg := range args {
		bld.WriteString(fmt.Sprint(arg))
	}
	if cloud == nil {
		cloudMu.Lock()
		cloudBuffer = append(cloudBuffer, bld.String())
		cloudMu.Unlock()
		return
	}
	cloudMu.Lock()
	for len(cloudBuffer) > 0 {
		b := cloudBuffer[0]
		cloudBuffer = cloudBuffer[1:]
		_, _ = cloud.Write([]byte(b))
	}
	cloudMu.Unlock()
	_, _ = cloud.Write([]byte(bld.String()))
}
