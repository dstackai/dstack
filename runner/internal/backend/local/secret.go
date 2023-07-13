package local

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"path/filepath"

	_ "modernc.org/sqlite"

	"github.com/dstackai/dstack/runner/internal/gerrors"
	"github.com/dstackai/dstack/runner/internal/log"
	"github.com/dstackai/dstack/runner/internal/models"
)

type ClientSecret struct {
	path string
}

func NewClientSecret(path string) *ClientSecret {
	return &ClientSecret{path: path}
}

func (sm *ClientSecret) fetchSecret(_ context.Context, path string, secrets map[string]string) (map[string]string, error) {
	db, err := sql.Open("sqlite", filepath.Join(sm.path, path, "_secrets_"))
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	defer func() { _ = db.Close() }()
	stmt, err := db.Prepare("SELECT secret_string FROM KV WHERE secret_name=?")
	if err != nil {
		return nil, gerrors.Wrap(err)
	}
	result := make(map[string]string)
	for secret, secretPath := range secrets {
		rows, err := stmt.Query(fmt.Sprintf("/dstack/secrets/%s", secretPath))
		if err != nil {
			return nil, gerrors.Wrap(err)
		}
		if rows.Next() {
			secretString := ""
			err = rows.Scan(&secretString)
			if err != nil {
				return nil, gerrors.Wrap(err)
			}
			result[secret] = secretString
		}
	}
	return result, nil
}

func (sm *ClientSecret) fetchCredentials(ctx context.Context, repoId string) *models.GitCredentials {
	db, err := sql.Open("sqlite", filepath.Join(sm.path, "repos", "_secrets_"))
	if err != nil {
		log.Error(ctx, "Connecting database. Credentials Local", "RepoId", repoId, "err", err)
		return nil
	}
	defer func() { _ = db.Close() }()
	rows, err := db.Query("SELECT secret_string FROM KV WHERE secret_name=?", fmt.Sprintf("/dstack/credentials/%s", repoId))
	if err != nil {
		log.Error(ctx, "Fetching value credentials Local", "RepoId", repoId, "err", err)
		return nil
	}
	if rows.Next() {
		secretString := ""
		err = rows.Scan(&secretString)
		if err != nil {
			log.Error(ctx, "Scan value credentials Local", "RepoId", repoId, "err", err)
			return nil
		}
		cred := new(models.GitCredentials)
		err = json.Unmarshal([]byte(secretString), &cred)
		if err != nil {
			log.Error(ctx, "Unmarshal value credentials Local", "RepoId", repoId, "err", err)
			return nil
		}
		return cred
	}
	log.Error(ctx, "GIT Credentials is empty")
	return nil
}
