package api

type LogsWriter struct {
	ch chan<- []byte
}

func NewLogsWriter(ch chan<- []byte) *LogsWriter {
	return &LogsWriter{ch: ch}
}

func (w *LogsWriter) Write(p []byte) (n int, err error) {
	p2 := make([]byte, len(p))
	copy(p2, p)
	w.ch <- p2
	return len(p), nil
}
