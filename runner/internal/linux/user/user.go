// Despite this package is being located inside the linux package, it should work on any Unix-like system.
package user

import (
	"fmt"
	osuser "os/user"
	"slices"
	"strconv"
	"syscall"
)

// User represents the user part of process `credentials(7)`
// (real user ID, real group ID, supplementary group IDs) enriched with
// some info from the user database `passwd(5)` (login name, home dir).
// Note, unlike the User struct from os/user, User does not necessarily
// correspond to any existing user account, for example, any of IDs may not exist
// in passwd(5) or group(5) databases at all or the user may not belong to
// the primary group or any of the specified supplementary groups.
type User struct {
	// Real user ID
	Uid int
	// Real group ID
	Gid int
	// Supplementary group IDs. The primary group should be always included and
	// the resulting list should be sorted in ascending order with duplicates removed;
	// NewUser() performs such normalization
	Gids []int
	// May be empty, e.g., if the user does not exist
	Username string
	// May be Empty, e.g., if the user does not exist
	HomeDir string
}

func (u *User) String() string {
	// The format is inspired by `id(1)`
	formattedUsername := ""
	if u.Username != "" {
		formattedUsername = fmt.Sprintf("(%s)", u.Username)
	}
	return fmt.Sprintf("uid=%d%s gid=%d groups=%v home=%s", u.Uid, formattedUsername, u.Gid, u.Gids, u.HomeDir)
}

func (u *User) ProcessCredentials() (*syscall.Credential, error) {
	if u.Uid < 0 {
		return nil, fmt.Errorf("negative user id: %d", u.Uid)
	}
	if u.Gid < 0 {
		return nil, fmt.Errorf("negative group id: %d", u.Gid)
	}
	groups := make([]uint32, len(u.Gids))
	for index, gid := range u.Gids {
		if gid < 0 {
			return nil, fmt.Errorf("negative supplementary group id: %d", gid)
		}
		groups[index] = uint32(gid)
	}
	creds := syscall.Credential{
		Uid:    uint32(u.Uid),
		Gid:    uint32(u.Gid),
		Groups: groups,
	}
	return &creds, nil
}

func (u *User) IsRoot() bool {
	return u.Uid == 0
}

func NewUser(uid int, gid int, gids []int, username string, homeDir string) *User {
	normalizedGids := append([]int{gid}, gids...)
	slices.Sort(normalizedGids)
	normalizedGids = slices.Compact(normalizedGids)
	return &User{
		Uid:      uid,
		Gid:      gid,
		Gids:     normalizedGids,
		Username: username,
		HomeDir:  homeDir,
	}
}

func FromCurrentProcess() (*User, error) {
	uid := syscall.Getuid()
	gid := syscall.Getgid()
	gids, err := syscall.Getgroups()
	if err != nil {
		return nil, fmt.Errorf("get supplementary groups: %w", err)
	}
	username := ""
	homeDir := ""
	if osUser, err := osuser.LookupId(strconv.Itoa(uid)); err == nil {
		username = osUser.Username
		homeDir = osUser.HomeDir
	}
	return NewUser(uid, gid, gids, username, homeDir), nil
}
