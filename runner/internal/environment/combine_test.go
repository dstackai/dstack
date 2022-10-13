package environment

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestCombine(t *testing.T) {
	s := map[string]interface{}{
		"FIRST": "1",
	}
	i := map[string]interface{}{
		"SECOND": 2,
	}
	r := Combine(s, i)
	assert.Equal(t, r, map[string]interface{}{
		"FIRST":  "1",
		"SECOND": 2,
	})
}
