package executor

import (
	"fmt"
	"strings"
)

func makeArgs(entrypoint []string, commands []string) []string {
	// todo env vars + secrets
	// todo if shell or docker entrypoint
	args := make([]string, len(entrypoint)-1)
	copy(args, entrypoint[1:])
	return append(args, joinShellCommands(commands)...)
}

func makeEnv(mapping map[string]string, secrets map[string]string) []string {
	list := make([]string, 0)
	for key, value := range mapping {
		list = append(list, fmt.Sprintf("%s=%s", key, value))
	}
	for key, value := range secrets {
		list = append(list, fmt.Sprintf("%s=%s", key, value))
	}
	return list
}

func joinShellCommands(commands []string) []string {
	if len(commands) == 0 {
		return []string{}
	}
	var sb strings.Builder
	for i, cmd := range commands {
		cmd := strings.TrimSpace(cmd)
		if i > 0 {
			sb.WriteString(" && ")
		}
		if strings.HasSuffix(cmd, "&") {
			sb.WriteString("{ ")
			sb.WriteString(cmd)
			sb.WriteString(" }")
		} else {
			sb.WriteString(cmd)
		}
	}
	return []string{sb.String()}
}
