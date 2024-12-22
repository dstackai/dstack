package executor

import (
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
