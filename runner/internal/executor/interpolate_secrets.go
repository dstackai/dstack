package executor

import (
	"context"
	"errors"
	"github.com/dstackai/dstack/runner/internal/log"
	"strings"
)

type SecretsInterpolator struct {
	Secrets map[string]string
}

func (si *SecretsInterpolator) Interpolate(ctx context.Context, value string) (string, error) {
	log.Trace(ctx, "Interpolating", "s", value)
	s := []rune(value)
	var sb strings.Builder

	start := 0
	for start < len(s) {
		dollar := IndexRuneSlice(s, '$', start)
		if dollar == -1 {
			sb.WriteString(string(s[start:]))
			break
		}
		sb.WriteString(string(s[start:dollar]))
		if dollar == len(s)-1 || (!isVarCharacter(s[dollar+1]) && s[dollar+1] != '{' && s[dollar+1] != '$') {
			return "", errors.New("unescaped $ sign")
		} else if s[dollar+1] == '$' {
			sb.WriteRune('$')
			start = start + 2
		} else if s[dollar+1] == '{' {
			end := IndexRuneSlice(s, '}', dollar+2)
			if end == -1 {
				return "", errors.New("unexpected EOL")
			}
			name := strings.TrimSpace(string(s[dollar+2 : end]))
			for _, c := range name {
				if !isVarCharacter(c) {
					return "", errors.New("$" + name + " contains illegal var characters")
				}
			}
			value, ok := si.Secrets[name]
			if ok {
				sb.WriteString(value)
			} else {
				log.Warning(ctx, "Variable is missing", "name", "$"+name)
			}
			start = end + 1
		} else {
			end := dollar + 1
			for end < len(s) && isVarCharacter(s[end]) {
				end++
			}
			name := strings.TrimSpace(string(s[dollar+1 : end]))
			value, ok := si.Secrets[name]
			if ok {
				sb.WriteString(value)
			} else {
				log.Warning(ctx, "Variable is missing", "name", "$"+name)
			}
			start = end
		}
	}
	return sb.String(), nil
}

func isVarCharacter(c rune) bool {
	if (c == '_') || ('0' <= c && c <= '9') || ('a' <= c && c <= 'z') || ('A' <= c && c <= 'Z') {
		return true
	}
	return false
}

func IndexRuneSlice(rs []rune, x rune, start int) int {
	for i, c := range rs[start:] {
		if c == x {
			return start + i
		}
	}
	return -1
}
