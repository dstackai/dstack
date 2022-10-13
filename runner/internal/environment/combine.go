package environment

func Combine(src ...map[string]interface{}) map[string]interface{} {
	c := make(map[string]interface{})
	for _, e := range src {
		if e != nil {
			for k, v := range e {
				c[k] = v
			}
		}
	}
	return c
}
