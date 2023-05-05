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
