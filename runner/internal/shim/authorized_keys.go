package shim

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"os/user"
	"path/filepath"
	"slices"

	"github.com/ztrue/tracerr"
	"golang.org/x/crypto/ssh"
)

func PublicKeyFingerprint(key string) (string, error) {
	pk, _, _, _, err := ssh.ParseAuthorizedKey([]byte(key))
	if err != nil {
		return "", tracerr.Wrap(err)
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

type AuthorizedKeys struct {
	user   string
	lookup func(username string) (*user.User, error)
}

func (ak AuthorizedKeys) AppendPublicKeys(publicKeys []string) error {
	return ak.transformAuthorizedKeys(AppendPublicKeys, publicKeys)
}

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
		return []string{}, tracerr.Wrap(err)
	}
	return lines, nil
}

func (ak AuthorizedKeys) write(w io.Writer, lines []string) error {
	wr := bufio.NewWriter(w)
	for _, line := range lines {
		_, err := fmt.Fprintln(wr, line)
		if err != nil {
			return tracerr.Wrap(err)
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
		return tracerr.Wrap(err)
	}

	info, err := os.Stat(authorizedKeysPath)
	if err != nil {
		return tracerr.Wrap(err)
	}
	fileMode := info.Mode().Perm()

	authorizedKeysFile, err := os.OpenFile(authorizedKeysPath, os.O_RDWR, fileMode)
	if err != nil {
		return tracerr.Wrap(err)
	}
	defer authorizedKeysFile.Close()

	lines, err := ak.read(authorizedKeysFile)
	if err != nil {
		return tracerr.Wrap(err)
	}

	// write backup
	authorizedKeysPath, err = ak.GetAuthorizedKeysPath()
	if err != nil {
		return tracerr.Wrap(err)
	}

	authorizedKeysPathBackup := authorizedKeysPath + ".bak"
	authorizedKeysBackup, err := os.OpenFile(authorizedKeysPathBackup, os.O_RDWR|os.O_CREATE|os.O_TRUNC, fileMode)
	if err != nil {
		return tracerr.Wrap(err)
	}
	defer authorizedKeysBackup.Close()
	if err := ak.write(authorizedKeysBackup, lines); err != nil {
		return tracerr.Wrap(err)
	}

	// transform lines
	newLines := transform(lines, publicKeys)

	// write authorized_keys
	if err := authorizedKeysFile.Truncate(0); err != nil {
		return tracerr.Wrap(err)
	}
	if _, err := authorizedKeysFile.Seek(0, 0); err != nil {
		return tracerr.Wrap(err)
	}
	if err := ak.write(authorizedKeysFile, newLines); err != nil {
		return tracerr.Wrap(err)
	}

	return nil
}
