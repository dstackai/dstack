package common

import "strings"

func String(value string) *string {
	return &value
}

func AddTrailingSlash(value string) string {
	if strings.HasSuffix(value, "/") {
		return value
	}
	return value + "/"
}

func IndexWithOffset(hay string, needle string, start int) int {
	idx := strings.Index(hay[start:], needle)
	if idx < 0 {
		return -1
	}
	return start + idx
}
