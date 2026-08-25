package shim

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/user"
	"path/filepath"
	"slices"
	"strings"

	"golang.org/x/crypto/ssh"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

// publicKeyMarker is appended to the comment field of every authorized_keys entry
// added by the shim, mirroring the `# added by dstack` marker the server writes when
// provisioning SSH fleets. sshd ignores everything after the key blob, so the marker
// has no effect on authentication; it only records that the entry is ours.
//
// Nothing honors the marker yet -- keys are still removed by fingerprint regardless of
// the comment. It is written now so that, once removal does honor it, entries added by
// earlier shim versions are already marked. Until then, a task can only be started and
// finalized by the same shim process, so there is no cross-version handoff to protect.
//
// The marker must be matched as an exact suffix: a substring match on `# added by
// dstack` would also claim the keys the server adds at fleet provisioning time, which
// the shim must never remove.
const publicKeyMarker = "# added by dstack-shim"

func PublicKeyFingerprint(key string) (string, error) {
	pk, _, _, _, err := ssh.ParseAuthorizedKey([]byte(key))
	if err != nil {
		return "", fmt.Errorf("parse authorized key: %w", err)
	}
	keyFingerprint := ssh.FingerprintSHA256(pk)
	return keyFingerprint, nil
}

func IsPublicKeysEqual(left string, right string) bool {
	leftFingerprint, err := PublicKeyFingerprint(left)
	if err != nil {
		return false
	}

	rightFingerprint, err := PublicKeyFingerprint(right)
	if err != nil {
		return false
	}

	return leftFingerprint == rightFingerprint
}

func RemovePublicKeys(fileKeys []string, keysToRemove []string) []string {
	newKeys := slices.DeleteFunc(fileKeys, func(fileKey string) bool {
		delete := slices.ContainsFunc(keysToRemove, func(removeKey string) bool {
			return IsPublicKeysEqual(fileKey, removeKey)
		})
		return delete
	})
	return newKeys
}

func AppendPublicKeys(fileKeys []string, keysToAppend []string) []string {
	newKeys := []string{}
	newKeys = append(newKeys, fileKeys...)
	newKeys = append(newKeys, keysToAppend...)
	return newKeys
}

// canonicalizePublicKey validates a public key received from the server and returns the
// authorized_keys line to write for it, marked with publicKeyMarker.
//
// The line is rebuilt from the parsed key instead of reusing the original entry, so that
// nothing unvalidated reaches the file.
func canonicalizePublicKey(publicKey string) (string, error) {
	key, comment, options, rest, err := ssh.ParseAuthorizedKey([]byte(publicKey))
	if err != nil {
		return "", fmt.Errorf("parse public key: %w", err)
	}
	// ParseAuthorizedKey stops at the end of the first key it finds
	if len(bytes.TrimSpace(rest)) > 0 {
		return "", errors.New("more than one key in a single entry")
	}
	// Options are a feature of the authorized_keys format, not of the on-disk public key
	// format, therefore an entry carrying them is not a public key
	if len(options) > 0 {
		return "", errors.New("unexpected authorized_keys options")
	}
	// MarshalAuthorizedKey returns a "<type> <base64>\n" line
	keyLine := strings.TrimSpace(string(ssh.MarshalAuthorizedKey(key)))
	// The comment cannot span lines, but may contain other whitespace, e.g., \t or \r
	commentFields := strings.Fields(comment)
	commentFields = append(commentFields, publicKeyMarker)
	return keyLine + " " + strings.Join(commentFields, " "), nil
}

type AuthorizedKeys struct {
	user   string
	lookup func(username string) (*user.User, error)
}

// AppendPublicKeys appends the keys to the user's authorized_keys file, marking them
// with publicKeyMarker. Invalid entries are skipped, so that one bad key does not keep
// the rest out of the file.
// Duplicates are not detected: a key already present in the file is appended once more.
func (ak AuthorizedKeys) AppendPublicKeys(ctx context.Context, publicKeys []string) error {
	lines := make([]string, 0, len(publicKeys))
	for _, publicKey := range publicKeys {
		line, err := canonicalizePublicKey(publicKey)
		if err != nil {
			// Whitespace is collapsed to keep the entry on a single log line
			log.Error(
				ctx, "skipping invalid public key",
				"key", strings.Join(strings.Fields(publicKey), " "), "err", err,
			)
			continue
		}
		lines = append(lines, line)
	}
	if len(lines) == 0 {
		return nil
	}
	return ak.transformAuthorizedKeys(AppendPublicKeys, lines)
}

// RemovePublicKeys removes the keys from the user's authorized_keys file, matching by
// fingerprint and ignoring the comment. That is, publicKeyMarker is not honored yet, so
// entries the shim did not add are removed as well, and every matching entry is removed
// even if another task still relies on the key. See dstackai/dstack#4174.
func (ak AuthorizedKeys) RemovePublicKeys(publicKeys []string) error {
	return ak.transformAuthorizedKeys(RemovePublicKeys, publicKeys)
}

func (ak AuthorizedKeys) read(r io.Reader) ([]string, error) {
	lines := []string{}
	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		text := scanner.Text()
		lines = append(lines, text)
	}
	if err := scanner.Err(); err != nil {
		return []string{}, fmt.Errorf("scan authorized keys: %w", err)
	}
	return lines, nil
}

func (ak AuthorizedKeys) write(w io.Writer, lines []string) error {
	wr := bufio.NewWriter(w)
	for _, line := range lines {
		_, err := fmt.Fprintln(wr, line)
		if err != nil {
			return fmt.Errorf("write line: %w", err)
		}
	}
	return wr.Flush()
}

func (ak AuthorizedKeys) GetHomeDirectory() (string, error) {
	usr, err := ak.lookup(ak.user)
	if err != nil {
		return "", err
	}
	return usr.HomeDir, nil
}

func (ak AuthorizedKeys) GetAuthorizedKeysPath() (string, error) {
	homeDir, err := ak.GetHomeDirectory()
	if err != nil {
		return "", err
	}
	return filepath.Join(homeDir, ".ssh", "authorized_keys"), nil
}

func (ak AuthorizedKeys) transformAuthorizedKeys(transform func([]string, []string) []string, publicKeys []string) error {
	authorizedKeysPath, err := ak.GetAuthorizedKeysPath()
	if err != nil {
		return fmt.Errorf("get authorized keys path: %w", err)
	}

	info, err := os.Stat(authorizedKeysPath)
	if err != nil {
		return fmt.Errorf("stat authorized keys: %w", err)
	}
	fileMode := info.Mode().Perm()

	authorizedKeysFile, err := os.OpenFile(authorizedKeysPath, os.O_RDWR, fileMode)
	if err != nil {
		return fmt.Errorf("open authorized keys: %w", err)
	}
	defer authorizedKeysFile.Close()

	lines, err := ak.read(authorizedKeysFile)
	if err != nil {
		return fmt.Errorf("read authorized keys: %w", err)
	}

	// write backup
	authorizedKeysPath, err = ak.GetAuthorizedKeysPath()
	if err != nil {
		return fmt.Errorf("get authorized keys path: %w", err)
	}

	authorizedKeysPathBackup := authorizedKeysPath + ".bak"
	authorizedKeysBackup, err := os.OpenFile(authorizedKeysPathBackup, os.O_RDWR|os.O_CREATE|os.O_TRUNC, fileMode)
	if err != nil {
		return fmt.Errorf("open authorized keys backup: %w", err)
	}
	defer authorizedKeysBackup.Close()
	if err := ak.write(authorizedKeysBackup, lines); err != nil {
		return fmt.Errorf("write authorized keys backup: %w", err)
	}

	// transform lines
	newLines := transform(lines, publicKeys)

	// write authorized_keys
	if err := authorizedKeysFile.Truncate(0); err != nil {
		return fmt.Errorf("truncate authorized keys: %w", err)
	}
	if _, err := authorizedKeysFile.Seek(0, 0); err != nil {
		return fmt.Errorf("seek authorized keys: %w", err)
	}
	if err := ak.write(authorizedKeysFile, newLines); err != nil {
		return fmt.Errorf("write authorized keys: %w", err)
	}

	return nil
}
