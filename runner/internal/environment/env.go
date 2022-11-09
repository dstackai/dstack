package environment

import (
	"fmt"
	"sync"
)

type Env struct {
	mu sync.Mutex
	m  map[string]interface{}
}

func New() *Env {
	return &Env{
		mu: sync.Mutex{},
		m:  make(map[string]interface{}),
	}
}

func (e *Env) AddMapString(src map[string]string) {
	if src == nil {
		return
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	for k, v := range src {
		e.m[k] = v
	}
}
func (e *Env) AddMapInterface(src map[string]interface{}) {
	if src == nil {
		return
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	for k, v := range src {
		e.m[k] = v
	}
}

func (e *Env) ToSlice() []string {
	e.mu.Lock()
	defer e.mu.Unlock()
	env := make([]string, 0)
	for k, v := range e.m {
		env = append(env, fmt.Sprintf("%s=%v", Normilize(k), v))
	}
	return env
}
