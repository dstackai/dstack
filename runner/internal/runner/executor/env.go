package executor

import (
	"context"
	"fmt"
	"strings"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

type EnvMap map[string]string

func (em EnvMap) Get(key string) string {
	return em[key]
}

func (em EnvMap) Update(src map[string]string, interpolate bool) {
	for key, value := range src {
		if interpolate {
			value = interpolateVariables(value, em.Get)
		}
		em[key] = value
	}
}

func (em EnvMap) Render() []string {
	var list []string
	for key, value := range em {
		list = append(list, fmt.Sprintf("%s=%s", key, value))
	}
	return list
}

func NewEnvMap(sources ...map[string]string) EnvMap {
	em := make(EnvMap)
	for _, src := range sources {
		em.Update(src, false)
	}
	return em
}

func ParseEnvList(list []string) EnvMap {
	em := make(EnvMap)
	for _, item := range list {
		parts := strings.SplitN(item, "=", 2)
		if len(parts) == 2 {
			em[parts[0]] = parts[1]
		}
	}
	return em
}

// sanitizeEnv removes variables that must not be propagated to `commands` and SSH sessions.
func sanitizeEnv(ctx context.Context, env map[string]string) {
	for name := range env {
		// Exported Bash functions are automatically "imported" by child shells, even in
		// POSIX mode. We remove such variables for consistency:
		//
		// * Even if we preserved them in `/dstack/profile`, they wouldn't work with
		//   non-login SSH sessions (`ssh run-name command arg1 arg2 ...`),
		//   as `/dstack/profile` is not sourced by non-login shells.
		// * Swapping `image` (e.g, `ubuntu` to `fedora`) or `shell` (e.g., `bash` to `sh`)
		//   in the run configuration should not change which functions are available in `commands`.
		//   If functions are essential for `commands`, the user should source them explicitly.
		//
		// See: https://github.com/dstackai/dstack/issues/4161
		if isBashFuncName(name) {
			log.Info(ctx, "Removed Bash exported function variable", "var", name)
			delete(env, name)
		}
	}
}

// isBashFuncName reports whether the variable name holds a body of a Bash function exported
// via `export -f foo`. Bash mangles the name to keep such variables out of the way of regular
// ones, the exact encoding depends on the version:
//
//   - `BASH_FUNC_foo%%` -- upstream Bash, that is, any reasonably modern distro.
//   - `BASH_FUNC_foo()` -- Red Hat's Bash 4.1/4.2 patch, that is, RHEL/CentOS 7 and older.
//
// Both encodings were introduced by the Shellshock patches. Bash without them exports the
// function as `foo`, which we deliberately don't detect: the name is indistinguishable from
// a regular variable, and, being a valid shell identifier, it doesn't break `/dstack/profile`.
func isBashFuncName(name string) bool {
	if !strings.HasPrefix(name, "BASH_FUNC_") {
		return false
	}
	return strings.HasSuffix(name, "%%") || strings.HasSuffix(name, "()")
}

// isShellIdentifier reports whether the variable name is a valid shell identifier, that is,
// whether `export NAME=value` is a valid command. Variables with other names are perfectly
// valid as far as execve(2) is concerned, but cannot be exported in `/dstack/profile`.
func isShellIdentifier(name string) bool {
	if name == "" || !isAlpha(name[0]) {
		return false
	}
	for i := 1; i < len(name); i++ {
		if !isAlphaNum(name[i]) {
			return false
		}
	}
	return true
}

// interpolateVariables expands variables as follows:
// `$VARNAME` -> literal `$VARNAME` (curly brackets are mandatory, bare $ means nothing)
// `${VARNAME}` -> getter("VARNAME") return value
// `$${VARNAME}` -> literal `${VARNAME}`
// `$$${VARNAME}` -> literal `$` + getter("VARNAME") return value
// `$$$${VARNAME}` -> literal `$${VARNAME}`
// `${no_closing_bracket`, `${0nonalphafirstchar}`, `${non-alphanum char}`, `${}` ->
// -> corresponding literal as is (only valid placeholder is treated specially requiring
// doubling $ to avoid interpolation, any non-valid syntax with `${` sequence is passed as is)
// See test cases for more examples
func interpolateVariables(s string, getter func(string) string) string {
	// assuming that most strings don't contain vars,
	// allocate the buffer the same size as input string
	buf := make([]byte, 0, len(s))
	dollarCount := 0
	for i := 0; i < len(s); i++ {
		switch char := s[i]; char {
		case '$':
			dollarCount += 1
		case '{':
			name, w := getVariableName(s[i+1:])
			if name != "" {
				// valid variable name, unescaping $
				for range dollarCount / 2 {
					buf = append(buf, '$')
				}
				if dollarCount%2 != 0 {
					// ${var} -> var_value, $$${var} -> $var_value
					buf = append(buf, getter(name)...)
				} else {
					// $${var} -> ${var}, $$$${var} -> $${var}
					buf = append(buf, s[i:i+w+1]...)
				}
			} else {
				// not a valid variable name or unclosed ${}, keeping all $ as is
				for range dollarCount {
					buf = append(buf, '$')
				}
				buf = append(buf, s[i:i+w+1]...)
			}
			i += w
			dollarCount = 0
		default:
			// flush accumulated $, if any
			for range dollarCount {
				buf = append(buf, '$')
			}
			dollarCount = 0
			buf = append(buf, char)
		}
	}
	// flush trailing $, if any
	for range dollarCount {
		buf = append(buf, '$')
	}
	return string(buf)
}

func getVariableName(s string) (string, int) {
	if len(s) < 2 {
		return "", len(s)
	}
	if !isAlpha(s[0]) {
		return "", 1
	}
	var i int
	for i = 1; i < len(s); i++ {
		char := s[i]
		if char == '}' {
			return s[:i], i + 1
		}
		if !isAlphaNum(char) {
			return "", i
		}
	}
	return "", i
}

func isAlpha(c uint8) bool {
	return c == '_' || 'a' <= c && c <= 'z' || 'A' <= c && c <= 'Z'
}

func isAlphaNum(c uint8) bool {
	return isAlpha(c) || '0' <= c && c <= '9'
}
