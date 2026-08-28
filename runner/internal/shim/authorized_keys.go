package shim

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"

	"golang.org/x/crypto/ssh"

	"github.com/dstackai/dstack/runner/internal/common/log"
)

// publicKeyMarker is appended to the comment field of every authorized_keys entry
// added by the shim, mirroring the `# added by dstack` marker the server writes when
// provisioning SSH fleets. sshd ignores everything after the key blob, so the marker
// has no effect on authentication; it only records that the entry is ours.
//
// The marker is what makes Reconcile() safe: only the entries carrying it are rewritten,
// so a key added by the user, or by the server at fleet provisioning time, is never
// touched. Entries added by a shim version that did not write the marker are kept
// forever; leaking a key we cannot prove we added beats revoking it.
//
// The marker must be matched as an exact suffix: a substring match on `# added by
// dstack` would also claim the keys the server adds at fleet provisioning time.
const publicKeyMarker = "# added by dstack-shim"

const (
	sshDirName             = ".ssh"
	authorizedKeysFileName = "authorized_keys"
	// Modes of the dir and the file when the shim creates them; an existing
	// authorized_keys file keeps its own mode
	sshDirMode             = 0o700
	authorizedKeysFileMode = 0o600
)

func PublicKeyFingerprint(key string) (string, error) {
	pk, _, _, _, err := ssh.ParseAuthorizedKey([]byte(key))
	if err != nil {
		return "", fmt.Errorf("parse authorized key: %w", err)
	}
	keyFingerprint := ssh.FingerprintSHA256(pk)
	return keyFingerprint, nil
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

// isShimEntry reports whether the authorized_keys line has been added by the shim, that
// is, whether it carries publicKeyMarker. canonicalizePublicKey() always puts the marker
// last, therefore matching it as a suffix cannot claim an entry that merely mentions it.
func isShimEntry(line string) bool {
	return strings.HasSuffix(strings.TrimRight(line, " \t\r"), " "+publicKeyMarker)
}

type AuthorizedKeys struct {
	user   string
	lookup func(username string) (*user.User, error)
}

// Reconcile makes the shim-owned part of the user's authorized_keys file exactly the
// given set of keys: the entries carrying publicKeyMarker are replaced with the entries
// for publicKeys. Everything else -- keys added by the user, keys added by the server
// when provisioning an SSH fleet, comments, blank lines -- is kept verbatim and in order.
//
// The keys of all the tasks that still need them are passed on every call, so that a task
// releasing a key shared with another task does not revoke it, see dstackai/dstack#4174.
// Duplicates collapse into a single entry, which is what makes the file depend on the set
// of keys in use and not on the number of tasks using them.
// A key that is also present as an entry the shim does not own is still written as an
// entry of its own: the two have different owners, and sharing one would let a manual
// edit revoke the access of a running task.
//
// Invalid keys are skipped, so that one bad key does not keep the rest out of the file.
func (ak AuthorizedKeys) Reconcile(ctx context.Context, publicKeys []string) error {
	usr, err := ak.lookup(ak.user)
	if err != nil {
		return fmt.Errorf("lookup user %s: %w", ak.user, err)
	}
	path := authorizedKeysPath(usr.HomeDir)

	lines, mode, err := readAuthorizedKeys(path)
	if err != nil {
		return err
	}
	kept := make([]string, 0, len(lines)+len(publicKeys))
	for _, line := range lines {
		if !isShimEntry(line) {
			kept = append(kept, line)
		}
	}
	kept = append(kept, shimEntries(ctx, publicKeys)...)

	return writeAuthorizedKeys(path, kept, mode, usr)
}

// shimEntries returns the marked authorized_keys lines to write for the keys, skipping
// the invalid ones and collapsing the duplicates
func shimEntries(ctx context.Context, publicKeys []string) []string {
	lines := make([]string, 0, len(publicKeys))
	seen := make(map[string]struct{}, len(publicKeys))
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
		// Matched by fingerprint and not by line, so that the same key submitted with
		// different comments does not yield two entries
		fingerprint, err := PublicKeyFingerprint(line)
		if err != nil {
			// canonicalizePublicKey() has already parsed the key, so this cannot happen
			log.Error(ctx, "failed to fingerprint canonicalized key", "err", err)
			continue
		}
		if _, ok := seen[fingerprint]; ok {
			continue
		}
		seen[fingerprint] = struct{}{}
		lines = append(lines, line)
	}
	return lines
}

// readAuthorizedKeys returns the lines of the file and its mode. A missing file is
// reported as an empty one with the mode to create it with: sshd treats it the same way,
// and the shim creates it as the server does when provisioning an SSH fleet.
func readAuthorizedKeys(path string) ([]string, os.FileMode, error) {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, authorizedKeysFileMode, nil
		}
		return nil, 0, fmt.Errorf("open authorized keys: %w", err)
	}
	defer file.Close()

	info, err := file.Stat()
	if err != nil {
		return nil, 0, fmt.Errorf("stat authorized keys: %w", err)
	}
	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		lines = append(lines, scanner.Text())
	}
	if err := scanner.Err(); err != nil {
		return nil, 0, fmt.Errorf("scan authorized keys: %w", err)
	}
	return lines, info.Mode().Perm(), nil
}

// writeAuthorizedKeys replaces the file with the given lines, creating it and its dir if
// they do not exist. The content is written to a temporary file in the same dir and
// renamed over the old one, so that a failed or interrupted write cannot leave the user
// with a partial file, that is, without some of their keys.
func writeAuthorizedKeys(path string, lines []string, mode os.FileMode, usr *user.User) (err error) {
	uid, gid, err := userIDs(usr)
	if err != nil {
		return err
	}
	dir := filepath.Dir(path)
	if _, statErr := os.Stat(dir); errors.Is(statErr, os.ErrNotExist) {
		if err := os.MkdirAll(dir, sshDirMode); err != nil {
			return fmt.Errorf("create %s: %w", dir, err)
		}
		// The shim normally runs as root, therefore a dir it creates must be given
		// to the user. An existing dir is left alone, as it is not ours to fix
		if err := os.Chown(dir, uid, gid); err != nil {
			return fmt.Errorf("chown %s: %w", dir, err)
		}
	}

	var content []byte
	if len(lines) > 0 {
		// The last line is terminated as well, so that appending to the file by hand
		// cannot join a new entry to the last one
		content = []byte(strings.Join(lines, "\n") + "\n")
	}
	tempPath := path + ".tmp"
	defer func() {
		if err != nil {
			// sshd does not read the temporary file, so leaving it behind would only
			// clutter the dir with a half-written copy of the user's keys
			if removeErr := os.Remove(tempPath); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
				err = errors.Join(err, fmt.Errorf("remove %s: %w", tempPath, removeErr))
			}
		}
	}()
	if err := writeFileSync(tempPath, content, mode); err != nil {
		return fmt.Errorf("write authorized keys: %w", err)
	}
	// The mode passed to writeFileSync() only applies to a file it creates, and is
	// masked by the umask, therefore it is set explicitly
	if err := os.Chmod(tempPath, mode); err != nil {
		return fmt.Errorf("chmod %s: %w", tempPath, err)
	}
	if err := os.Chown(tempPath, uid, gid); err != nil {
		return fmt.Errorf("chown %s: %w", tempPath, err)
	}
	if err := os.Rename(tempPath, path); err != nil {
		return fmt.Errorf("rename %s: %w", tempPath, err)
	}
	return nil
}

// userIDs returns the numeric ids of the user. os/user reports them as strings, since
// not all platforms have numeric ids, but Linux, the only platform the shim runs on, does
func userIDs(usr *user.User) (int, int, error) {
	uid, err := strconv.Atoi(usr.Uid)
	if err != nil {
		return 0, 0, fmt.Errorf("parse uid %q of user %s: %w", usr.Uid, usr.Username, err)
	}
	gid, err := strconv.Atoi(usr.Gid)
	if err != nil {
		return 0, 0, fmt.Errorf("parse gid %q of user %s: %w", usr.Gid, usr.Username, err)
	}
	return uid, gid, nil
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
	return authorizedKeysPath(homeDir), nil
}

func authorizedKeysPath(homeDir string) string {
	return filepath.Join(homeDir, sshDirName, authorizedKeysFileName)
}
