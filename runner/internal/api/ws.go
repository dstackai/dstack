package api

import (
	"context"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/gorilla/websocket"
	"net/http"
	"time"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

func (s *Server) logsWsGetHandler(w http.ResponseWriter, r *http.Request) (int, string) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Error(r.Context(), "Failed to upgrade connection", "err", err)
		return http.StatusInternalServerError, ""
	}
	// todo memorize clientId?
	go s.streamJobLogs(conn)
	return 200, "ok"
}

func (s *Server) streamJobLogs(conn *websocket.Conn) {
	currentPos := 0
	defer func() {
		_ = conn.WriteMessage(websocket.CloseMessage, nil)
		_ = conn.Close()
	}()

	for {
		s.executor.RLock()
		jobLogsHistory := s.executor.GetJobLogsHistory()
		select {
		case <-s.shutdownCh:
			if currentPos >= len(jobLogsHistory) {
				s.executor.RUnlock()
				//s.logsDoneCh <- nil
				return
			}
		default:
			if currentPos >= len(jobLogsHistory) {
				s.executor.RUnlock()
				time.Sleep(100 * time.Millisecond)
			}
		}
		for currentPos < len(jobLogsHistory) {
			if err := conn.WriteMessage(websocket.BinaryMessage, jobLogsHistory[currentPos].Message); err != nil {
				s.executor.RUnlock()
				log.Error(context.TODO(), "Failed to write message", "err", err)
				return
			}
			currentPos++
		}
		s.executor.RUnlock()
	}
}
