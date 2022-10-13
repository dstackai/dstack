package environment

import (
	"sort"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestEnvToSlice(t *testing.T) {
	e := New()
	e.AddMapString(map[string]string{
		"FIRST": "1",
	})
	e.AddMapInterface(map[string]interface{}{
		"SECOND": 2,
	})
	slice := e.ToSlice()
	sort.Strings(slice)
	assert.Equal(t, slice, []string{
		"FIRST=1",
		"SECOND=2",
	})
}
