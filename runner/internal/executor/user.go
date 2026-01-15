package executor

import (
	"context"
	"errors"
	"fmt"
	"os"
	osuser "os/user"
	"path"
	"strconv"
	"strings"

	linuxuser "github.com/dstackai/dstack/runner/internal/linux/user"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/schemas"
)

func (ex *RunExecutor) setJobUser(ctx context.Context) error {
	if ex.jobSpec.User == nil {
		// JobSpec.User is nil if the user is not specified either in the dstack configuration
		// (the `user` property) or in the image (the `USER` Dockerfile instruction).
		// In such cases, the root user should be used as a fallback, and we use the current user,
		// assuming that the runner is started by root.
		ex.jobUser = &ex.currentUser
	} else {
		jobUser, err := jobUserFromJobSpecUser(
			ex.jobSpec.User,
			osuser.LookupId, osuser.Lookup,
			osuser.LookupGroup, (*osuser.User).GroupIds,
		)
		if err != nil {
			return fmt.Errorf("job user from job spec: %w", err)
		}
		ex.jobUser = jobUser
	}

	if err := checkHomeDir(ex.jobUser.HomeDir); err != nil {
		log.Warning(ctx, "Error while checking job user home dir, using / instead", "err", err)
		ex.jobUser.HomeDir = "/"
	}

	log.Trace(ctx, "Job user", "user", ex.jobUser)
	return nil
}

func jobUserFromJobSpecUser(
	jobSpecUser *schemas.User,
	userLookupIdFunc func(string) (*osuser.User, error),
	userLookupNameFunc func(string) (*osuser.User, error),
	groupLookupNameFunc func(string) (*osuser.Group, error),
	userGroupIdsFunc func(*osuser.User) ([]string, error),
) (*linuxuser.User, error) {
	if jobSpecUser.Uid == nil && jobSpecUser.Username == nil {
		return nil, errors.New("neither uid nor username is set")
	}

	var err error
	var osUser *osuser.User

	// -1 is a placeholder value, the actual value must be >= 0
	//nolint:ineffassign
	uid := -1
	if jobSpecUser.Uid != nil {
		uid = int(*jobSpecUser.Uid)
		osUser, err = userLookupIdFunc(strconv.Itoa(uid))
		if err != nil {
			var notFoundErr osuser.UnknownUserIdError
			if !errors.As(err, &notFoundErr) {
				return nil, fmt.Errorf("lookup user by id: %w", err)
			}
		}
	} else {
		osUser, err = userLookupNameFunc(*jobSpecUser.Username)
		if err != nil {
			return nil, fmt.Errorf("lookup user by name: %w", err)
		}
		uid, err = parseStringId(osUser.Uid)
		if err != nil {
			return nil, fmt.Errorf("parse user id: %w", err)
		}
	}
	if uid == -1 {
		// Assertion, should never occur
		return nil, errors.New("failed to infer user id")
	}

	// -1 is a placeholder value, the actual value must be >= 0
	//nolint:ineffassign
	gid := -1
	// Must include at least one gid, see len(gids) == 0 assertion below
	var gids []int
	if jobSpecUser.Gid != nil {
		gid = int(*jobSpecUser.Gid)
		// Here and below:
		// > Note that when specifying a group for the user, the user will have
		// > only the specified group membership.
		// > Any other configured group memberships will be ignored.
		// See: https://docs.docker.com/reference/dockerfile/#user
		gids = []int{gid}
	} else if jobSpecUser.Groupname != nil {
		osGroup, err := groupLookupNameFunc(*jobSpecUser.Groupname)
		if err != nil {
			return nil, fmt.Errorf("lookup group by name: %w", err)
		}
		gid, err = parseStringId(osGroup.Gid)
		if err != nil {
			return nil, fmt.Errorf("parse group id: %w", err)
		}
		gids = []int{gid}
	} else if osUser != nil {
		gid, err = parseStringId(osUser.Gid)
		if err != nil {
			return nil, fmt.Errorf("parse group id: %w", err)
		}
		rawGids, err := userGroupIdsFunc(osUser)
		if err != nil {
			return nil, fmt.Errorf("get user supplementary group ids: %w", err)
		}
		// [main_gid, supplementary_gid_1, supplementary_gid_2, ...]
		gids = make([]int, len(rawGids)+1)
		gids[0] = gid
		for index, rawGid := range rawGids {
			supplementaryGid, err := parseStringId(rawGid)
			if err != nil {
				return nil, fmt.Errorf("parse supplementary group id: %w", err)
			}
			gids[index+1] = supplementaryGid
		}
	} else {
		// > When the user doesn't have a primary group then the image
		// > (or the next instructions) will be run with the root group.
		// See: https://docs.docker.com/reference/dockerfile/#user
		gid = 0
		gids = []int{gid}
	}
	if gid == -1 {
		// Assertion, should never occur
		return nil, errors.New("failed to infer group id")
	}
	if len(gids) == 0 {
		// Assertion, should never occur
		return nil, errors.New("failed to infer supplementary group ids")
	}

	username := ""
	homeDir := ""
	if osUser != nil {
		username = osUser.Username
		homeDir = osUser.HomeDir
	}

	return linuxuser.NewUser(uid, gid, gids, username, homeDir), nil
}

func parseStringId(stringId string) (int, error) {
	id, err := strconv.Atoi(stringId)
	if err != nil {
		return 0, err
	}
	if id < 0 {
		return 0, fmt.Errorf("negative id value: %d", id)
	}
	return id, nil
}

func checkHomeDir(homeDir string) error {
	if homeDir == "" {
		return errors.New("not set")
	}
	if !path.IsAbs(homeDir) {
		return fmt.Errorf("must be absolute: %s", homeDir)
	}
	if info, err := os.Stat(homeDir); errors.Is(err, os.ErrNotExist) {
		if strings.Contains(homeDir, "nonexistent") {
			// let `/nonexistent` stay non-existent
			return fmt.Errorf("non-existent: %s", homeDir)
		}
	} else if err != nil {
		return err
	} else if !info.IsDir() {
		return fmt.Errorf("not a directory: %s", homeDir)
	}
	return nil
}
