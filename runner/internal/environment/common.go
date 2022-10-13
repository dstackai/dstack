package environment

import "strings"

func Normilize(src string) string {
	src = strings.ToUpper(src)
	bld := new(strings.Builder)
	for _, ch := range src {
		if (ch >= 'A' && ch <= 'Z') ||
			(ch >= '0' && ch <= '9') {
			bld.WriteRune(ch)
		} else {
			bld.WriteByte('_')
		}
	}
	return bld.String()
}
