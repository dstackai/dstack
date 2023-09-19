package common

import "strings"

func IndexWithOffset(hay string, needle string, start int) int {
	idx := strings.Index(hay[start:], needle)
	if idx < 0 {
		return -1
	}
	return start + idx
}
