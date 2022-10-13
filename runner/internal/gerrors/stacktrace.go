package gerrors

import (
	"errors"
	"fmt"
	"path/filepath"
	"runtime"
	"strings"
)

type withStack struct {
	err        error
	pointFrame uintptr
}

func (ws withStack) Error() string {
	if ws.pointFrame == 0 {
		return ws.err.Error()
	}

	f := getFrame(ws.pointFrame)
	if f.File == "" {
		return "[unknown] " + ws.err.Error()
	}

	_, file := filepath.Split(f.File)
	l := fmt.Sprintf("%s:%d", file, f.Line)
	if f.Function != "" {
		idx := strings.LastIndex(f.Function, "/")
		l += " " + f.Function[idx+1:]
	}
	return fmt.Sprintf("[%s] %s", l, ws.err)
}

func (ws withStack) Unwrap() error {
	return ws.err
}

func New(s string) error {
	return withStack{
		err:        errors.New(s),
		pointFrame: pointFrame(),
	}
}

func Newf(format string, a ...interface{}) error {
	return withStack{
		err:        fmt.Errorf(format, a...),
		pointFrame: pointFrame(),
	}
}

func Wrap(err error) error {
	if err == nil {
		return nil
	}
	return withStack{
		err:        err,
		pointFrame: pointFrame(),
	}
}

func pointFrame() uintptr {
	pc := make([]uintptr, 1)
	runtime.Callers(3, pc)
	return pc[0]
}

func getFrame(pc uintptr) *runtime.Frame {
	f, _ := runtime.CallersFrames([]uintptr{pc}).Next()
	return &f
}
