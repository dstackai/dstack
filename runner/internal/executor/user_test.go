package executor

import (
	"errors"
	osuser "os/user"
	"strconv"
	"testing"

	"github.com/stretchr/testify/require"

	linuxuser "github.com/dstackai/dstack/runner/internal/linux/user"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

var shouldNotBeCalledErr = errors.New("this function should not be called")

func unknownUserIdError(t *testing.T, strUid string) osuser.UnknownUserIdError {
	t.Helper()
	uid, err := strconv.Atoi(strUid)
	require.NoError(t, err)
	return osuser.UnknownUserIdError(uid)
}

func TestJobUserFromJobSpecUser_Uid_UserDoesNotExist(t *testing.T) {
	specUid := uint32(2000)
	specUser := schemas.User{Uid: &specUid}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      0,
		Gids:     []int{0},
		Username: "",
		HomeDir:  "",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, unknownUserIdError(t, id) },
		func(name string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Uid_Gid_UserDoesNotExist(t *testing.T) {
	specUid := uint32(2000)
	specGid := uint32(200)
	specUser := schemas.User{Uid: &specUid, Gid: &specGid}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      200,
		Gids:     []int{200},
		Username: "",
		HomeDir:  "",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, unknownUserIdError(t, id) },
		func(name string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Uid_UserExists(t *testing.T) {
	specUid := uint32(2000)
	specUser := schemas.User{Uid: &specUid}
	osUser := osuser.User{
		Uid:      "2000",
		Gid:      "300",
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}
	osUserGids := []string{"300", "400", "500"}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      300,
		Gids:     []int{300, 400, 500},
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(uid string) (*osuser.User, error) { return &osUser, nil },
		func(name string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(gid string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return osUserGids, nil },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Uid_Gid_UserExists(t *testing.T) {
	specUid := uint32(2000)
	specGid := uint32(200)
	specUser := schemas.User{Uid: &specUid, Gid: &specGid}
	osUser := osuser.User{
		Uid:      "2000",
		Gid:      "300",
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      200,
		Gids:     []int{200},
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return &osUser, nil },
		func(name string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Username_UserDoesNotExist(t *testing.T) {
	specUsername := "unknownuser"
	specUser := schemas.User{Username: &specUsername}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.User, error) { return nil, osuser.UnknownUserError(name) },
		func(name string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.ErrorContains(t, err, "lookup user by name")
	require.Nil(t, user)
}

func TestJobUserFromJobSpecUser_Username_UserExists(t *testing.T) {
	specUsername := "testnuser"
	specUser := schemas.User{Username: &specUsername}
	osUser := osuser.User{
		Uid:      "2000",
		Gid:      "300",
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}
	osUserGids := []string{"300", "400", "500"}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      300,
		Gids:     []int{300, 400, 500},
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.User, error) { return &osUser, nil },
		func(name string) (*osuser.Group, error) { return nil, shouldNotBeCalledErr },
		func(*osuser.User) ([]string, error) { return osUserGids, nil },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Username_Groupname_UserExists_GroupExists(t *testing.T) {
	specUsername := "testnuser"
	specGroupname := "testgroup"
	specUser := schemas.User{Username: &specUsername, Groupname: &specGroupname}
	osUser := osuser.User{
		Uid:      "2000",
		Gid:      "300",
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}
	osGroup := osuser.Group{
		Gid:  "200",
		Name: specGroupname,
	}
	expectedUser := linuxuser.User{
		Uid:      2000,
		Gid:      200,
		Gids:     []int{200},
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.User, error) { return &osUser, nil },
		func(name string) (*osuser.Group, error) { return &osGroup, nil },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.NoError(t, err)
	require.Equal(t, expectedUser, *user)
}

func TestJobUserFromJobSpecUser_Username_Groupname_UserExists_GroupDoesNotExist(t *testing.T) {
	specUsername := "testnuser"
	specGroupname := "testgroup"
	specUser := schemas.User{Username: &specUsername, Groupname: &specGroupname}
	osUser := osuser.User{
		Uid:      "2000",
		Gid:      "300",
		Username: "testuser",
		HomeDir:  "/home/testuser",
	}

	user, err := jobUserFromJobSpecUser(
		&specUser,
		func(id string) (*osuser.User, error) { return nil, shouldNotBeCalledErr },
		func(name string) (*osuser.User, error) { return &osUser, nil },
		func(name string) (*osuser.Group, error) { return nil, osuser.UnknownGroupError(name) },
		func(*osuser.User) ([]string, error) { return nil, shouldNotBeCalledErr },
	)

	require.ErrorContains(t, err, "lookup group by name")
	require.Nil(t, user)
}
