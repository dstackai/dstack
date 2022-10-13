package stream

import (
	"context"
	"fmt"
	"net/http"
	"sync"

	"github.com/gorilla/websocket"
	"gitlab.com/dstackai/dstackai-runner/internal/gerrors"
	"gitlab.com/dstackai/dstackai-runner/internal/log"
)

const (
	cliIDParam = "cli"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

type Server struct {
	buf    [][]byte
	client sync.Map
	mu     sync.RWMutex
	port   int
	closed chan struct{}
}

func New(port int) *Server {
	s := &Server{
		buf:    make([][]byte, 0),
		client: sync.Map{},
		mu:     sync.RWMutex{},
		port:   port,
		closed: make(chan struct{}),
	}
	return s
}

func (s *Server) Run(ctx context.Context) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/logsws", s.getLogs)
	if err := http.ListenAndServe(fmt.Sprintf(":%d", s.port), mux); err != nil {
		log.Error(ctx, "HTTP server error", "err", err)
		return gerrors.Wrap(err)
	}
	return nil
}

func (s *Server) Close() {
	select {
	case <-s.closed:
		return
	default:

	}
	close(s.closed)
}

func (s *Server) Write(p []byte) (int, error) {
	s.mu.Lock()
	dst := make([]byte, len(p))
	copy(dst, p)
	s.buf = append(s.buf, dst)
	s.mu.Unlock()
	return len(p), nil
}

func (s *Server) getLogs(w http.ResponseWriter, r *http.Request) {
	connection, _ := upgrader.Upgrade(w, r, nil)
	var currentPos int
	var hasID bool
	var clientID string
	if r.URL.Query().Has(cliIDParam) {
		clientID = r.URL.Query().Get(cliIDParam)
		pos, ok := s.client.Load(clientID)
		if ok {
			switch v := pos.(type) {
			case int:
				currentPos = v
			}
		}
		hasID = true
	}
	for {
		s.mu.RLock()
		select {
		case <-s.closed:
			if currentPos == len(s.buf) {
				_ = connection.WriteMessage(websocket.CloseMessage, nil)
				_ = connection.Close()
				s.mu.RUnlock()
				return
			}
		default:
		}
		if currentPos == len(s.buf) {
			s.mu.RUnlock()
			continue
		}
		_ = connection.WriteMessage(websocket.TextMessage, s.buf[currentPos])
		currentPos++
		s.mu.RUnlock()
		if hasID {
			s.client.Store(clientID, currentPos)
		}
	}
}
