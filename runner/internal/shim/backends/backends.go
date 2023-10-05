package backends

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/gerrors"
	"sync"
)

type Backend interface {
	Terminate(context.Context) error
}

type BackendFactory func(ctx context.Context) (Backend, error)

var backends = make(map[string]BackendFactory)
var mu = sync.Mutex{}

func NewBackend(ctx context.Context, name string) (Backend, error) {
	mu.Lock()
	defer mu.Unlock()
	factory, ok := backends[name]
	if !ok {
		return nil, gerrors.Newf("unknown backend %s", name)
	}
	return factory(ctx)
}

func register(name string, factory BackendFactory) {
	mu.Lock()
	defer mu.Unlock()
	backends[name] = factory
}
