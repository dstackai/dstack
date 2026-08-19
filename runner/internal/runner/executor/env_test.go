package executor

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func dummyGetter(s string) string {
	return "<dummy>"
}

func TestInterpolateVariables_DollarEscape(t *testing.T) {
	testCases := []struct {
		input, expected string
	}{
		{"", ""},
		{"just a string", "just a string"},
		{"$ $$ $$$", "$ $$ $$$"},
		{"foo $notavar", "foo $notavar"},
		{"foo $$notavar", "foo $$notavar"},
		{"trailing$", "trailing$"},
		{"trailing$$", "trailing$$"},
		{"trailing${", "trailing${"},
		{"trailing$${", "trailing$${"},
		{"empty${}", "empty${}"},
		{"empty${}empty", "empty${}empty"},
		{"empty$${}empty", "empty$${}empty"},
		{"foo${notavar", "foo${notavar"},
		{"foo${notavar bar", "foo${notavar bar"},
		{"foo$${notavar", "foo$${notavar"},
		{"foo$${notavar bar", "foo$${notavar bar"},
		{"foo${!notavar}", "foo${!notavar}"},
		{"foo${!notavar}bar", "foo${!notavar}bar"},
		{"foo${not!a!var}", "foo${not!a!var}"},
		{"foo$${not!a!var}", "foo$${not!a!var}"},
		{"foo${not!a!var}bar", "foo${not!a!var}bar"},
		{"foo$${not!a!var}bar", "foo$${not!a!var}bar"},
		{"${0notavar}", "${0notavar}"},
		{"foo ${0notavar}bar", "foo ${0notavar}bar"},
		{"foo $$${0notavar}bar", "foo $$${0notavar}bar"},
		{"foo$${escaped}", "foo${escaped}"},
		{"foo$$$${escaped}bar", "foo$${escaped}bar"},
		{"${var}", "<dummy>"},
		{"$$${var}", "$<dummy>"},
		{"$$${var}$", "$<dummy>$"},
		{"$$${var}$$", "$<dummy>$$"},
		{"foo${var}bar", "foo<dummy>bar"},
		{"hi ${var_WITH_all_allowed_char_types_013}", "hi <dummy>"},
	}
	for _, tc := range testCases {
		interpolated := interpolateVariables(tc.input, dummyGetter)
		assert.Equal(t, tc.expected, interpolated)
	}
}

func TestEnvMapUpdate_Expand(t *testing.T) {
	envMap := EnvMap{"PATH": "/bin:/sbin"}
	envMap.Update(EnvMap{"PATH": "/opt/bin:${PATH}"}, true)
	assert.Equal(t, EnvMap{"PATH": "/opt/bin:/bin:/sbin"}, envMap)
}

func TestEnvMapUpdate_Expand_NoCurlyBrackets(t *testing.T) {
	envMap := EnvMap{"PATH": "/bin:/sbin"}
	envMap.Update(EnvMap{"PATH": "/opt/bin:$PATH"}, true)
	assert.Equal(t, EnvMap{"PATH": "/opt/bin:$PATH"}, envMap)
}

func TestEnvMapUpdate_Expand_MissingVar(t *testing.T) {
	envMap := EnvMap{}
	envMap.Update(EnvMap{"PATH": "/opt/bin:${PATH}"}, true)
	assert.Equal(t, EnvMap{"PATH": "/opt/bin:"}, envMap)
}

func TestEnvMapUpdate_Expand_VarLike(t *testing.T) {
	envMap := EnvMap{}
	envMap.Update(EnvMap{"TOKEN": "deadf00d${notavar ${$NOTaVAR}"}, true)
	assert.Equal(t, EnvMap{"TOKEN": "deadf00d${notavar ${$NOTaVAR}"}, envMap)
}

func TestEnvMapUpdate_Merge_NoExpand(t *testing.T) {
	envMap := EnvMap{
		"VAR1": "var1_oldvalue",
		"VAR2": "var2_value",
	}
	envMap.Update(map[string]string{
		"VAR1": "var1_newvalue",
		"VAR3": "var3_${VAR2}",
	}, false)

	expected := EnvMap{
		"VAR1": "var1_newvalue",
		"VAR2": "var2_value",
		"VAR3": "var3_${VAR2}",
	}
	assert.Equal(t, expected, envMap)
}

func TestEnvMapUpdate_Merge_Expand(t *testing.T) {
	envMap := EnvMap{
		"VAR1": "var1_oldvalue",
		"VAR2": "var2_value",
	}
	envMap.Update(map[string]string{
		"VAR1": "var1_newvalue",
		"VAR3": "var3_${VAR2}",
	}, true)

	expected := EnvMap{
		"VAR1": "var1_newvalue",
		"VAR2": "var2_value",
		"VAR3": "var3_var2_value",
	}
	assert.Equal(t, expected, envMap)
}

func TestIsBashFuncName(t *testing.T) {
	testCases := []struct {
		name     string
		expected bool
	}{
		// upstream Bash
		{"BASH_FUNC_foo%%", true},
		{"BASH_FUNC_ml%%", true},
		// Bash function names are not limited to shell identifiers
		{"BASH_FUNC_foo-bar%%", true},
		{"BASH_FUNC_foo.bar()", true},
		// Red Hat's Bash 4.1/4.2 (RHEL/CentOS 7 and older)
		{"BASH_FUNC_module()", true},
		// no function name, still not a valid identifier
		{"BASH_FUNC_%%", true},
		{"BASH_FUNC_()", true},
		// regular variables
		{"", false},
		{"PATH", false},
		{"BASH_FUNC_foo", false},
		{"BASH_FUNC_", false},
		{"bash_func_foo%%", false},
		{"FOO%%", false},
		{"FOO()", false},
	}
	for _, tc := range testCases {
		assert.Equal(t, tc.expected, isBashFuncName(tc.name), tc.name)
	}
}

func TestIsShellIdentifier(t *testing.T) {
	testCases := []struct {
		name     string
		expected bool
	}{
		{"VAR", true},
		{"_", true},
		{"_var1", true},
		{"VAR_1_2", true},
		{"", false},
		{"1VAR", false},
		{"VAR-1", false},
		{"VAR 1", false},
		{"VAR.1", false},
		{"BASH_FUNC_foo%%", false},
		{"BASH_FUNC_foo()", false},
	}
	for _, tc := range testCases {
		assert.Equal(t, tc.expected, isShellIdentifier(tc.name), tc.name)
	}
}

func TestSanitizeEnv(t *testing.T) {
	env := EnvMap{
		"PATH":                 "/bin:/sbin",
		"BASH_FUNC_NOT_A_FUNC": "just a variable",
		"BASH_FUNC_ml%%":       "() {  eval $($LMOD_DIR/ml_cmd \"$@\")\n}",
		"BASH_FUNC_module()":   "() {  eval $($LMOD_CMD bash \"$@\")\n}",
	}

	sanitizeEnv(context.Background(), env)

	expected := EnvMap{
		"PATH":                 "/bin:/sbin",
		"BASH_FUNC_NOT_A_FUNC": "just a variable",
	}
	assert.Equal(t, expected, env)
}

func TestSanitizeEnv_Empty(t *testing.T) {
	env := EnvMap{}
	sanitizeEnv(context.Background(), env)
	assert.Equal(t, EnvMap{}, env)
}
