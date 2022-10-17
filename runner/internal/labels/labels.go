package labels

import (
	"github.com/dstackai/dstackai/runner/internal/models"
)

func Combine(l ...map[string]string) map[string]string {
	c := make(map[string]string)
	for _, m := range l {
		if m != nil {
			for k, v := range m {
				c[k] = v
			}
		}
	}
	return c
}

func Main() map[string]string {
	return map[string]string{
		"ai.dstack": "true",
	}
}

func FromJob(job *models.Job) map[string]string {
	return map[string]string{
		"ai.dstack.job.id":        job.JobID,
		"ai.dstack.job.name":      job.RunName,
		"ai.dstack.repo.hash":     job.RepoHash,
		"ai.dstack.repo.username": job.RepoUserName,
		"ai.dstack.repo.diff":     job.RepoDiff,
	}
}
