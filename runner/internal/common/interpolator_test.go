package common

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestPlainText(t *testing.T) {
	var vi VariablesInterpolator
	s := "plain text"
	result, err := vi.Interpolate(context.Background(), s)
	assert.Equal(t, nil, err)
	assert.Equal(t, s, result)
}

func TestMissingVariable(t *testing.T) {
	var vi VariablesInterpolator
	result, err := vi.Interpolate(context.Background(), "${{ VAR_NAME }} is here")
	assert.Equal(t, nil, err)
	assert.Equal(t, " is here", result)
}

func TestDollarEscape(t *testing.T) {
	var vi VariablesInterpolator
	result, err := vi.Interpolate(context.Background(), "it is not a variable $$!")
	assert.Equal(t, nil, err)
	assert.Equal(t, "it is not a variable $!", result)
}

func TestDollarWithoutEscape(t *testing.T) {
	var vi VariablesInterpolator
	result, err := vi.Interpolate(context.Background(), "it is not a variable $!")
	assert.Equal(t, nil, err)
	assert.Equal(t, "it is not a variable $!", result)
}

func TestEscapeOpening(t *testing.T) {
	var vi VariablesInterpolator
	result, err := vi.Interpolate(context.Background(), "$${{ VAR_NAME }}")
	assert.Equal(t, nil, err)
	assert.Equal(t, "${{ VAR_NAME }}", result)
}

func TestWithoutClosing(t *testing.T) {
	var vi VariablesInterpolator
	_, err := vi.Interpolate(context.Background(), "the end ${{")
	assert.NotEqual(t, nil, err)
}

func TestUnexpectedEOL(t *testing.T) {
	var vi VariablesInterpolator
	_, err := vi.Interpolate(context.Background(), "the end ${{ VAR }")
	assert.NotEqual(t, nil, err)
}

func TestSecrets(t *testing.T) {
	var vi VariablesInterpolator
	vi.Add("secrets", map[string]string{"user": "qwerty"})
	result, err := vi.Interpolate(context.Background(), "${{ secrets.user }}")
	assert.Equal(t, nil, err)
	assert.Equal(t, "qwerty", result)
}
