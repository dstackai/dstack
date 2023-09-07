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
		s.historyMutex.RLock()
		select {
		case <-s.shutdown:
			if currentPos >= len(s.jobLogsHistory) {
				s.historyMutex.RUnlock()
				return
			}
		default:
			if currentPos >= len(s.jobLogsHistory) {
				s.historyMutex.RUnlock()
				time.Sleep(100 * time.Millisecond)
			}
		}
		for currentPos < len(s.jobLogsHistory) {
			if err := conn.WriteMessage(websocket.BinaryMessage, s.jobLogsHistory[currentPos].Message); err != nil {
				s.historyMutex.RUnlock()
				log.Error(context.TODO(), "Failed to write message", "err", err)
				return
			}
			currentPos++
		}
		s.historyMutex.RUnlock()
	}
}
