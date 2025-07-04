package api

import (
	"context"
	"net/http"
	"time"

	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

func (s *Server) logsWsGetHandler(w http.ResponseWriter, r *http.Request) (interface{}, error) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		return nil, err
	}
	// todo memorize clientId?
	go s.streamJobLogs(conn)
	return nil, nil
}

func (s *Server) streamJobLogs(conn *websocket.Conn) {
	currentPos := 0
	defer func() {
		_ = conn.WriteMessage(websocket.CloseMessage, nil)
		_ = conn.Close()
	}()

	for {
		s.executor.RLock()
		jobLogsWsHistory := s.executor.GetJobWsLogsHistory()
		select {
		case <-s.shutdownCh:
			if currentPos >= len(jobLogsWsHistory) {
				s.executor.RUnlock()
				close(s.wsDoneCh)
				return
			}
		default:
			if currentPos >= len(jobLogsWsHistory) {
				s.executor.RUnlock()
				time.Sleep(100 * time.Millisecond)
				continue
			}
		}
		for currentPos < len(jobLogsWsHistory) {
			if err := conn.WriteMessage(websocket.BinaryMessage, jobLogsWsHistory[currentPos].Message); err != nil {
				s.executor.RUnlock()
				log.Error(context.TODO(), "Failed to write message", "err", err)
				return
			}
			currentPos++
		}
		s.executor.RUnlock()
	}
}
