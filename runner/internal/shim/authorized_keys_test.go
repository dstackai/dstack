package shim

import (
	"fmt"
	"os"
	"os/user"
	"path"
	"testing"

	"github.com/stretchr/testify/require"
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

func TestIsPublicKeysEqual(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"

	result := IsPublicKeysEqual(keyLeft, keyRight)
	require.True(t, result)
}

func TestIsPublicKeysEqualBrokenKey(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAP66um5MadfhB5dSnEM= thebits@barracuda"

	resultFwd := IsPublicKeysEqual(keyLeft, keyRight)
	require.False(t, resultFwd)

	resultBck := IsPublicKeysEqual(keyRight, keyLeft)
	require.False(t, resultBck)
}

func TestIsPublicKeysNotEqual(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"

	result := IsPublicKeysEqual(keyLeft, keyRight)
	require.False(t, result)
}

func TestRemovePublicKeys(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"

	keys := []string{keyLeft, keyRight}
	newKeys := RemovePublicKeys(keys, []string{keyRight})

	require.Len(t, newKeys, 1)
	require.Equal(t, newKeys, []string{keyLeft})
}

func TestRemovePublicKeysRemoveAll(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"

	keys := []string{keyLeft, keyRight}
	newKeys := RemovePublicKeys(keys, []string{keyRight, keyLeft})

	require.Empty(t, newKeys)
}

func TestRemovePublicKeysRemoveNotContained(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"

	keys := []string{keyLeft, keyRight}
	newKeys := RemovePublicKeys(keys, []string{"# line with comment"})

	require.Equal(t, keys, newKeys)
}

func TestAppendPublicKeys(t *testing.T) {
	keyLeft := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	keyRight := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"
	comment := "# line with coment"

	keys := []string{keyLeft, keyRight}
	newKeys := AppendPublicKeys(keys, []string{comment})

	require.Equal(t, []string{keyLeft, keyRight, comment}, newKeys)
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
		} else {
			require.NoError(t, err)
			require.Equal(t, tc.expected, filePath)
		}
	}
}

func TestAppendKey(t *testing.T) {
	ak := AuthorizedKeys{user: "test_user", lookup: mockUserLookup}
	filePath, err := ak.GetAuthorizedKeysPath()
	require.NoError(t, err)

	err = os.MkdirAll(path.Dir(filePath), os.ModePerm)
	require.NoError(t, err)

	key := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	err = os.WriteFile(filePath, []byte(key), os.ModePerm)
	require.NoError(t, err)

	commentLine := "# comment line"
	err = ak.AppendPublicKeys([]string{commentLine})
	require.NoError(t, err)

	b, err := os.ReadFile(filePath)
	require.NoError(t, err)
	require.Contains(t, string(b), commentLine)
}

func TestRemoveKey(t *testing.T) {
	ak := AuthorizedKeys{user: "test_user", lookup: mockUserLookup}
	filePath, err := ak.GetAuthorizedKeysPath()
	require.NoError(t, err)

	err = os.MkdirAll(path.Dir(filePath), os.ModePerm)
	require.NoError(t, err)

	key := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	err = os.WriteFile(filePath, []byte(key), os.ModePerm)
	require.NoError(t, err)

	err = ak.RemovePublicKeys([]string{key})
	require.NoError(t, err)

	b, err := os.ReadFile(filePath)
	require.NoError(t, err)
	require.Empty(t, string(b))

	back, err := os.ReadFile(filePath + ".bak")
	require.NoError(t, err)
	require.Contains(t, string(back), key)
}

func TestRemoveTwoKey(t *testing.T) {
	ak := AuthorizedKeys{user: "test_user", lookup: mockUserLookup}
	filePath, err := ak.GetAuthorizedKeysPath()
	require.NoError(t, err)

	err = os.MkdirAll(path.Dir(filePath), os.ModePerm)
	require.NoError(t, err)

	first := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	second := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"
	third := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDIAGg0prDVeane6xLvMPBKQHxNUpt4q/hmuAAxjOUW0GWMPS2qE3l8YkmWeK80nKvio4M/IYWe67HIVeibdvKPoFJTtgm93WeJT9KD6h7MCschAf78mAIBhzUMK+9UYl5pE2jpfqc0SXkUsXDxMVN+ST9lN7fXUVsCPXO6qJG+0hLA3vs5r0aY1Td72vI4h45DhwjdpYkY1KTNJwfSwyvZpoN9n85JjaqXsjLG/NhieDBKu0VJE1a44aWuFwmULmpDZcUcWtk074pPMMvuh/Go5gbTaIf1gsniBKNLrfTeGjIHE/Hu9o1G3GGpq6CDqOjb0ykukWZbD2qfV0gERwIR dstack"

	err = os.WriteFile(filePath, []byte(first+"\n"+second+"\n"+third), os.ModePerm)
	require.NoError(t, err)

	err = ak.RemovePublicKeys([]string{first, third})
	require.NoError(t, err)

	b, err := os.ReadFile(filePath)
	require.NoError(t, err)
	require.NotContains(t, string(b), first)
	require.NotContains(t, string(b), third)
	require.Contains(t, string(b), second)
}

func TestAppendTwoKey(t *testing.T) {
	ak := AuthorizedKeys{user: "test_user", lookup: mockUserLookup}
	filePath, err := ak.GetAuthorizedKeysPath()
	require.NoError(t, err)

	err = os.MkdirAll(path.Dir(filePath), os.ModePerm)
	require.NoError(t, err)

	first := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCdqa9VimGtCppxtz6T0kXfA6csnRlGS0zmTNvH2XCIYYbNFcymjL1SpFXfYQvXrnoK7nR+4dHP66um5Mi4OWHC1pB4t2OPYNnEYuYJ/VFpPv0/ykGAijV+IZjh6wS5r1o/EfiG8kMlv2TGhDb/jjsJXl9zb3i0urTrG0Sk6iw7F7QL/pXUe1cKuhdxOUzw/ddNZ5fBCikAr2cYfI0kiqe4U/pRSV5mPNAuQvBFK+K7UDdKfKIf4YxTFjXFbcgD7XUC5nInhIdSvGFYLdHSuafwWz8Q5ds/EyAPCyMU2wsA+AIP5XpdIraJLDTQT1J4PjcYwecNibWU2rkobl9FDVcflZq+0s0HbmJRlB4uExTNRZP7ykMKp9MtJsQGB6uA41KYNsvV5a+7SX39syNDHGTB13gHQHmYEHgSmHIcyEE2tEh7Zb6OAFCsytUKzBl51FIS3V70ve9kqJUcldBEkGJh6PeFOvYQZ95Gl2Uob0ujKCVDrzMylepnadfhB5dSnEM= thebits@barracuda"
	second := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCfAFHwfyMKPFbKq+D/vYNaXjqer4uV5+zvlrPY2bvkdRT4GiH4hm2s1Z7+fUEYQBNfw5O9SgxGotqyguUJbuVUc2BCNdD8HC3PxKtEev35ga4G3jjyuVeHcL2T9pn+F8IW1o3SpDGATAHJyFtArPYz31Hwg6PiuggPNdPLMSzZNrwNVuPwT1uDMKFqAh+1ryIVi7389fjZ7aBR9F06VIPpWIVVKqSVD+NbHtwWqCw8AsprJE3bPwVW09OJeQX8GXryKasaX4t4HMXmO/UI8tprnyf05dAl7NQOPY9Iut5PgfzEVY/T0M1RSnZi7i+1x7WBWX3aMM/Hv+NUeX2YtuAN"
	third := "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDIAGg0prDVeane6xLvMPBKQHxNUpt4q/hmuAAxjOUW0GWMPS2qE3l8YkmWeK80nKvio4M/IYWe67HIVeibdvKPoFJTtgm93WeJT9KD6h7MCschAf78mAIBhzUMK+9UYl5pE2jpfqc0SXkUsXDxMVN+ST9lN7fXUVsCPXO6qJG+0hLA3vs5r0aY1Td72vI4h45DhwjdpYkY1KTNJwfSwyvZpoN9n85JjaqXsjLG/NhieDBKu0VJE1a44aWuFwmULmpDZcUcWtk074pPMMvuh/Go5gbTaIf1gsniBKNLrfTeGjIHE/Hu9o1G3GGpq6CDqOjb0ykukWZbD2qfV0gERwIR dstack"

	err = os.WriteFile(filePath, []byte(first), os.ModePerm)
	require.NoError(t, err)

	err = ak.AppendPublicKeys([]string{second, third})
	require.NoError(t, err)

	b, err := os.ReadFile(filePath)
	require.NoError(t, err)
	require.Contains(t, string(b), first)
	require.Contains(t, string(b), second)
	require.Contains(t, string(b), third)
}
