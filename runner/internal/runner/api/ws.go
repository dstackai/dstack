package api

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/gorilla/websocket"

	"github.com/dstackai/dstack/runner/internal/log"
)

type logsWsRequestParams struct {
	startTimestamp int64
}

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
	requestParams, err := parseRequestParams(r)
	if err != nil {
		_ = conn.WriteMessage(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseUnsupportedData, err.Error()),
		)
		_ = conn.Close()
		return nil, nil
	}
	// todo memorize clientId?
	go s.streamJobLogs(r.Context(), conn, requestParams)
	return nil, nil
}

func parseRequestParams(r *http.Request) (logsWsRequestParams, error) {
	query := r.URL.Query()
	startTimeStr := query.Get("start_time")
	var startTimestamp int64
	if startTimeStr != "" {
		t, err := time.Parse(time.RFC3339, startTimeStr)
		if err != nil {
			return logsWsRequestParams{}, errors.New("failed to parse start_time value")
		}
		startTimestamp = t.Unix()
	}
	return logsWsRequestParams{startTimestamp: startTimestamp}, nil
}

func (s *Server) streamJobLogs(ctx context.Context, conn *websocket.Conn, params logsWsRequestParams) {
	defer func() {
		_ = conn.WriteMessage(websocket.CloseMessage, nil)
		_ = conn.Close()
	}()
	currentPos := 0
	startTimestampMs := params.startTimestamp * 1000
	if startTimestampMs != 0 {
		// TODO: Replace currentPos linear search with binary search
		s.executor.RLock()
		jobLogsWsHistory := s.executor.GetJobWsLogsHistory()
		for _, logEntry := range jobLogsWsHistory {
			if logEntry.Timestamp < startTimestampMs {
				currentPos += 1
			} else {
				break
			}
		}
		s.executor.RUnlock()
	}
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
				log.Error(ctx, "failed to write message", "err", err)
				return
			}
			currentPos++
		}
		s.executor.RUnlock()
	}
}
