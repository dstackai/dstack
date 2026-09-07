package shim

import (
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"testing"

	"github.com/stretchr/testify/require"
)

// Two valid keys, used to build authorized_keys entries. Short on purpose: the blob is
// noise in a test that is about the lines around it
const (
	testKeyOne = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGYzO2yHhoIzYHnGH5CT/hpTNGRHvJHkKQlXqPZ0Uxwj"
	testKeyTwo = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILuLmyPGV/gcatBaZFxRPKGQVJ4vBjuqEsHIkKGrGZKS"
)

func TestPublicKeyFingerprint(t *testing.T) {
	key := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	expectedFingerprint := "SHA256:9HymzYAtJKNh8gKufl3EVoRSauL4E7Mbmuzqlcvii50"
	fingerprint, err := PublicKeyFingerprint(key)
	require.NoError(t, err)
	require.Equal(t, expectedFingerprint, fingerprint)
}

func TestPublicKeyFingerprintError(t *testing.T) {
	key := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQ= thebits@barracuda"
	fingerprint, err := PublicKeyFingerprint(key)
	require.Error(t, err)
	require.Empty(t, fingerprint)
}

func mockUserLookup(username string) (*user.User, error) {
	if username == "test_user" {
		return &user.User{
			Username: "test_user",
			HomeDir:  "/tmp/home/test_user",
		}, nil
	}
	if username == "test_user2" {
		return &user.User{
			Username: "test_user2",
			HomeDir:  "/tmp/home/test_user2",
		}, nil
	}
	return nil, fmt.Errorf("user not found")
}

func TestGetAuthorizedKeysPath(t *testing.T) {
	testCases := []struct {
		user     string
		exists   bool
		expected string
		isError  bool
	}{
		{
			user:     "test_user",
			exists:   true,
			expected: "/tmp/home/test_user/.ssh/authorized_keys",
			isError:  false,
		},
		{
			user:     "test_user2",
			exists:   true,
			expected: "/tmp/home/test_user2/.ssh/authorized_keys",
			isError:  false,
		},
		{
			user:     "test_user3",
			exists:   false,
			expected: "",
			isError:  true,
		},
	}

	for _, tc := range testCases {
		ak := AuthorizedKeys{user: tc.user, lookup: mockUserLookup}
		filePath, err := ak.GetAuthorizedKeysPath()
		if tc.isError {
			require.Error(t, err)
			require.Equal(t, tc.expected, filePath)
		} else {
			require.NoError(t, err)
			require.Equal(t, tc.expected, filePath)
		}
	}
}

func TestCanonicalizePublicKey(t *testing.T) {
	const blob = testKeyOne

	testCases := []struct {
		name     string
		key      string
		expected string
		isError  bool
	}{
		{
			name:     "with comment",
			key:      blob + " user@host",
			expected: blob + " user@host # added by dstack-shim",
		},
		{
			name:     "without comment",
			key:      blob,
			expected: blob + " # added by dstack-shim",
		},
		{
			name:     "surrounding whitespace",
			key:      "  " + blob + "\tuser@host \r\n",
			expected: blob + " user@host # added by dstack-shim",
		},
		{
			name:    "two keys in one entry",
			key:     blob + " user@host\n" + blob + " user@host",
			isError: true,
		},
		{
			name: "authorized_keys options",
			// options are not part of the on-disk public key format
			key:     `restrict,command="/bin/false" ` + blob + " user@host",
			isError: true,
		},
		{
			name:    "comment line",
			key:     "# comment line",
			isError: true,
		},
		{
			name:    "malformed",
			key:     "ssh-ed25519 AAAAP66um5MadfhB5dSnEM=",
			isError: true,
		},
		{
			name:    "empty",
			key:     "",
			isError: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			line, err := canonicalizePublicKey(tc.key)
			if tc.isError {
				require.Error(t, err)
				require.Empty(t, line)
			} else {
				require.NoError(t, err)
				require.Equal(t, tc.expected, line)
			}
		})
	}
}

func TestIsShimEntry(t *testing.T) {
	testCases := []struct {
		name     string
		line     string
		expected bool
	}{
		{
			name:     "shim entry",
			line:     testKeyOne + " user@host # added by dstack-shim",
			expected: true,
		},
		{
			name:     "shim entry without comment",
			line:     testKeyOne + " # added by dstack-shim",
			expected: true,
		},
		{
			name:     "trailing whitespace",
			line:     testKeyOne + " # added by dstack-shim  \r",
			expected: true,
		},
		{
			// the marker the server writes when provisioning an SSH fleet is a prefix of
			// ours, and the keys it marks must never be touched by the shim
			name:     "server entry",
			line:     testKeyOne + " user@host # added by dstack",
			expected: false,
		},
		{
			name:     "user entry",
			line:     testKeyOne + " user@host",
			expected: false,
		},
		{
			name:     "marker not at the end",
			line:     testKeyOne + " # added by dstack-shim user@host",
			expected: false,
		},
		{
			name:     "blank line",
			line:     "",
			expected: false,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			require.Equal(t, tc.expected, isShimEntry(tc.line))
		})
	}
}

// newTestAuthorizedKeys returns an AuthorizedKeys for a user whose home is a temp dir,
// along with the path of their authorized_keys file. The mocked lookup reports the ids of
// the current process, so that setting the ownership of the file succeeds without root
func newTestAuthorizedKeys(t *testing.T) (AuthorizedKeys, string) {
	t.Helper()
	usr := &user.User{
		Username: "test_user",
		HomeDir:  t.TempDir(),
		Uid:      strconv.Itoa(os.Getuid()),
		Gid:      strconv.Itoa(os.Getgid()),
	}
	ak := AuthorizedKeys{
		user: usr.Username,
		lookup: func(username string) (*user.User, error) {
			if username != usr.Username {
				return nil, fmt.Errorf("user not found")
			}
			return usr, nil
		},
	}
	return ak, authorizedKeysPath(usr.HomeDir)
}

func writeTestAuthorizedKeys(t *testing.T, path string, content string) {
	t.Helper()
	require.NoError(t, os.MkdirAll(filepath.Dir(path), sshDirMode))
	require.NoError(t, os.WriteFile(path, []byte(content), authorizedKeysFileMode))
}

func TestReconcile(t *testing.T) {
	const (
		marker = " # added by dstack-shim"
		// an entry added by the user by hand, which the shim must never remove
		manual = testKeyOne + " added-by-hand"
		// an entry added by the server when provisioning an SSH fleet
		server = testKeyTwo + " dstack # added by dstack"
	)

	testCases := []struct {
		name     string
		content  string
		keys     []string
		expected string
	}{
		{
			name:     "adds an entry",
			content:  "",
			keys:     []string{testKeyOne + " user@host"},
			expected: testKeyOne + " user@host" + marker + "\n",
		},
		{
			name:     "removes an entry that is no longer in use",
			content:  testKeyOne + marker + "\n",
			keys:     nil,
			expected: "",
		},
		{
			name:     "keeps an entry that is still in use",
			content:  testKeyOne + " user@host" + marker + "\n",
			keys:     []string{testKeyOne + " user@host"},
			expected: testKeyOne + " user@host" + marker + "\n",
		},
		{
			// the whole point of dstackai/dstack#4174: two co-located tasks share a key,
			// and the one that finishes first must not revoke it for the other
			name:     "collapses a key used more than once into one entry",
			content:  "",
			keys:     []string{testKeyOne + " first", testKeyOne + " second"},
			expected: testKeyOne + " first" + marker + "\n",
		},
		{
			name:     "keeps the entries the shim does not own",
			content:  "# a comment\n\n" + manual + "\n" + server + "\n",
			keys:     nil,
			expected: "# a comment\n\n" + manual + "\n" + server + "\n",
		},
		{
			name:     "keeps a key added by hand and used by a task as two entries",
			content:  manual + "\n",
			keys:     []string{testKeyOne + " user@host"},
			expected: manual + "\n" + testKeyOne + " user@host" + marker + "\n",
		},
		{
			name:     "removes only the entries the shim owns",
			content:  manual + "\n" + testKeyTwo + marker + "\n" + server + "\n",
			keys:     nil,
			expected: manual + "\n" + server + "\n",
		},
		{
			name:     "skips an invalid key without dropping the valid ones",
			content:  "",
			keys:     []string{"not a key", testKeyOne + "\n" + testKeyTwo, testKeyTwo},
			expected: testKeyTwo + marker + "\n",
		},
		{
			name:     "terminates the last line of a file without a trailing newline",
			content:  manual,
			keys:     nil,
			expected: manual + "\n",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			ak, path := newTestAuthorizedKeys(t)
			writeTestAuthorizedKeys(t, path, tc.content)

			require.NoError(t, ak.Reconcile(t.Context(), tc.keys))

			content, err := os.ReadFile(path)
			require.NoError(t, err)
			require.Equal(t, tc.expected, string(content))
		})
	}
}

func TestReconcileCreatesMissingFile(t *testing.T) {
	ak, path := newTestAuthorizedKeys(t)

	require.NoError(t, ak.Reconcile(t.Context(), []string{testKeyOne}))

	content, err := os.ReadFile(path)
	require.NoError(t, err)
	require.Equal(t, testKeyOne+" # added by dstack-shim\n", string(content))
	fileInfo, err := os.Stat(path)
	require.NoError(t, err)
	require.Equal(t, os.FileMode(authorizedKeysFileMode), fileInfo.Mode().Perm())
	dirInfo, err := os.Stat(filepath.Dir(path))
	require.NoError(t, err)
	require.Equal(t, os.FileMode(sshDirMode), dirInfo.Mode().Perm())
}

func TestReconcileKeepsFileMode(t *testing.T) {
	ak, path := newTestAuthorizedKeys(t)
	writeTestAuthorizedKeys(t, path, "")
	require.NoError(t, os.Chmod(path, 0o644))

	require.NoError(t, ak.Reconcile(t.Context(), []string{testKeyOne}))

	fileInfo, err := os.Stat(path)
	require.NoError(t, err)
	require.Equal(t, os.FileMode(0o644), fileInfo.Mode().Perm())
	// sshd does not read the temporary file, so leaving it behind would only make the
	// next call write to a stale one
	_, err = os.Stat(path + ".tmp")
	require.ErrorIs(t, err, os.ErrNotExist)
}

func TestReconcileUnknownUser(t *testing.T) {
	ak := AuthorizedKeys{user: "no_such_user", lookup: mockUserLookup}

	require.Error(t, ak.Reconcile(t.Context(), []string{testKeyOne}))
}
