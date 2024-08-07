package common

import (
	"context"
	"fmt"
	"strings"

	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
)

const (
	PatternOpening = "${{"
	PatternClosing = "}}"
)

type VariablesInterpolator struct {
	Variables map[string]string
}

func (vi *VariablesInterpolator) Add(namespace string, vars map[string]string) {
	if vi.Variables == nil {
		vi.Variables = make(map[string]string, len(vars))
	}
	for k, v := range vars {
		vi.Variables[fmt.Sprintf("%s.%s", namespace, k)] = v
	}
}

func (vi *VariablesInterpolator) Interpolate(ctx context.Context, s string) (string, error) {
	log.Trace(ctx, "Interpolating", "s", s)
	var sb strings.Builder

	start := 0
	for start < len(s) {
		dollar := IndexWithOffset(s, "$", start)
		if dollar == -1 || dollar == len(s)-1 {
			sb.WriteString(s[start:])
			break
		}
		if s[dollar+1] == '$' { // $$ = escaped $
			sb.WriteString(s[start : dollar+1])
			start = dollar + 2
			continue
		}

		opening := IndexWithOffset(s, PatternOpening, start)
		if opening == -1 {
			sb.WriteString(s[start:])
			break
		}
		sb.WriteString(s[start:opening])
		closing := IndexWithOffset(s, PatternClosing, opening)
		if closing == -1 {
			return "", gerrors.Newf("no pattern closing: %s", s[opening:])
		}

		name := strings.TrimSpace(s[opening+len(PatternOpening) : closing])
		value, ok := vi.Variables[name]
		if ok {
			sb.WriteString(value)
		} else {
			log.Warning(ctx, "Variable is missing", "name", name)
		}
		start = closing + len(PatternClosing)
	}
	return sb.String(), nil
}
