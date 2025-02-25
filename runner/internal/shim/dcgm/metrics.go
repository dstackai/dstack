package dcgm

import (
	"bufio"
	"bytes"
	"strings"
)

// FilterMetrics returns subset of metrics filtered by GPU UUIDs
func FilterMetrics(expfmtBody []byte, uuids []string) []byte {
	// DCGM Exporter returns metrics in the following format:
	// # HELP DCGM_FIELD_1 Docstring for field 1
	// # TYPE DCGM_FIELD_1 gauge|counter|...
	// DCGM_FIELD{gpu="0", UUID="..." [...other labels...]} 0.0
	// DCGM_FIELD{gpu="1", UUID="..." [...other labels...]} 0.5
	// ...
	// HELP DCGM_FIELD_2 Docstring for field 2
	// ...
	var buffer bytes.Buffer
	scanner := bufio.NewScanner(bytes.NewReader(expfmtBody))
	helpComment := ""
	typeComment := ""
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if len(line) == 0 {
			continue
		}
		if strings.HasPrefix(line, "# HELP") {
			helpComment = line
			continue
		}
		if strings.HasPrefix(line, "# TYPE") {
			typeComment = line
			continue
		}
		if strings.HasPrefix(line, "#") {
			continue
		}
		for _, uuid := range uuids {
			if strings.Contains(line, uuid) {
				if helpComment != "" {
					buffer.WriteString(helpComment)
					buffer.WriteRune('\n')
					helpComment = ""
				}
				if typeComment != "" {
					buffer.WriteString(typeComment)
					buffer.WriteRune('\n')
					typeComment = ""
				}
				buffer.WriteString(line)
				buffer.WriteRune('\n')
			}
		}
	}
	return buffer.Bytes()
}
