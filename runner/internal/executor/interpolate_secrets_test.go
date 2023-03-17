package executor

import (
	"context"
	"github.com/stretchr/testify/assert"
	"testing"
)

func TestPlainText(t *testing.T) {
	si := SecretsInterpolator{}
	s := "plain text"
	result, err := si.Interpolate(context.Background(), s)
	assert.Equal(t, nil, err)
	assert.Equal(t, s, result)
}

func TestMissingVariable(t *testing.T) {
	si := SecretsInterpolator{}
	result, err := si.Interpolate(context.Background(), "$VAR_NAME is here")
	assert.Equal(t, nil, err)
	assert.Equal(t, " is here", result)
}

func TestDollarEscape(t *testing.T) {
	si := SecretsInterpolator{}
	result, err := si.Interpolate(context.Background(), "it is not a variable $$!")
	assert.Equal(t, nil, err)
	assert.Equal(t, "it is not a variable $!", result)
}

func TestChain(t *testing.T) {
	si := SecretsInterpolator{
		Secrets: map[string]string{"VAR_A": "aaa", "VAR_B": "bbb"},
	}
	result, err := si.Interpolate(context.Background(), "chain $VAR_A$VAR_B")
	assert.Equal(t, nil, err)
	assert.Equal(t, "chain aaabbb", result)
}

func TestBrackets(t *testing.T) {
	si := SecretsInterpolator{
		Secrets: map[string]string{"VAR_A": "aaa", "VAR_B": "bbb"},
	}
	result, err := si.Interpolate(context.Background(), "password: '${VAR_A}'")
	assert.Equal(t, nil, err)
	assert.Equal(t, "password: 'aaa'", result)
}

func TestBracketsWithSpaces(t *testing.T) {
	si := SecretsInterpolator{
		Secrets: map[string]string{"VAR_A": "aaa", "VAR_B": "bbb"},
	}
	result, err := si.Interpolate(context.Background(), " ${VAR_A    }")
	assert.Equal(t, nil, err)
	assert.Equal(t, " aaa", result)
}

func TestUnescapedDollar(t *testing.T) {
	si := SecretsInterpolator{}
	_, err := si.Interpolate(context.Background(), "the end$")
	assert.NotEqual(t, nil, err)
}

func TestIllegalCharacter(t *testing.T) {
	si := SecretsInterpolator{}
	_, err := si.Interpolate(context.Background(), "${VAR-NAME}")
	assert.NotEqual(t, nil, err)
}

func TestUnexpectedEOL(t *testing.T) {
	si := SecretsInterpolator{}
	_, err := si.Interpolate(context.Background(), "${VARNAME")
	assert.NotEqual(t, nil, err)
}
