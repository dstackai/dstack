package log

import (
	"testing"

	"github.com/sirupsen/logrus"
	"github.com/stretchr/testify/require"
)

func TestParseLevel(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  int
	}{
		{name: "digit 1", input: "1", want: int(logrus.FatalLevel)},
		{name: "digit 2", input: "2", want: int(logrus.ErrorLevel)},
		{name: "digit 3", input: "3", want: int(logrus.WarnLevel)},
		{name: "digit 4", input: "4", want: int(logrus.InfoLevel)},
		{name: "digit 5", input: "5", want: int(logrus.DebugLevel)},
		{name: "digit 6", input: "6", want: int(logrus.TraceLevel)},
		{name: "fatal", input: "fatal", want: int(logrus.FatalLevel)},
		{name: "error", input: "error", want: int(logrus.ErrorLevel)},
		{name: "warn", input: "warn", want: int(logrus.WarnLevel)},
		{name: "warning", input: "warning", want: int(logrus.WarnLevel)},
		{name: "info", input: "info", want: int(logrus.InfoLevel)},
		{name: "debug", input: "debug", want: int(logrus.DebugLevel)},
		{name: "trace", input: "trace", want: int(logrus.TraceLevel)},
		{name: "uppercase", input: "INFO", want: int(logrus.InfoLevel)},
		{name: "mixed case", input: "Debug", want: int(logrus.DebugLevel)},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseLevel(tt.input)
			require.NoError(t, err)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestParseLevelError(t *testing.T) {
	tests := []struct {
		name  string
		input string
	}{
		{name: "empty", input: ""},
		{name: "unknown word", input: "verbose"},
		{name: "panic out of range", input: "panic"},
		{name: "digit 0 out of range", input: "0"},
		{name: "digit 7 out of range", input: "7"},
		{name: "digit 9 out of range", input: "9"},
		{name: "multi-digit", input: "10"},
		{name: "negative digit", input: "-1"},
		{name: "non-ascii digit", input: "౧"},
		{name: "digit with whitespace", input: "4 "},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := ParseLevel(tt.input)
			require.Error(t, err)
		})
	}
}
