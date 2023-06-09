package container

import (
	"bytes"
	"context"
	"fmt"
	"github.com/docker/docker/api/types"
	"os"
	"path/filepath"
	"testing"
)

func Test_Prebuild_Save_Load(t *testing.T) {
	engine := NewEngine()
	if engine == nil {
		t.Skip("Can't create engine")
	}
	spec := &PrebuildSpec{
		BaseImageName: "dstackai/miniforge:py3.7-0.1",
		WorkDir:       "/workflow",
		Commands: []string{
			"pip install --no-cache-dir tqdm",
			"echo qwerty > /root/prebuild",
		},
		Entrypoint: []string{"bash", "-i", "-c"},
		RepoPath:   filepath.Join(t.TempDir(), "src"),
	}
	if err := os.Mkdir(spec.RepoPath, 0o755); err != nil {
		t.Error(err)
	}
	name, err := engine.GetPrebuildName(context.TODO(), spec)
	if err != nil {
		t.Error("GetPrebuildName:", err)
	}
	imageName := fmt.Sprintf("dstackai/test-prebuild:%s", name)
	diffPath := filepath.Join(t.TempDir(), fmt.Sprintf("%s.tar", name))

	err = engine.Prebuild(context.TODO(), spec, imageName, diffPath, os.Stdout, &bytes.Buffer{})
	if err != nil {
		t.Error("Prebuild & Save:", err)
	}
	t.Cleanup(func() {
		_, _ = engine.client.ImageRemove(context.TODO(), imageName, types.ImageRemoveOptions{Force: true})
	})

	prebuildInspect, _, err := engine.client.ImageInspectWithRaw(context.TODO(), imageName)
	if err != nil {
		t.Error("Prebuild inspect:", err)
	}
	_, err = engine.client.ImageRemove(context.TODO(), imageName, types.ImageRemoveOptions{Force: true})
	if err != nil {
		t.Error("Prebuild remove:", err)
	}

	err = engine.UsePrebuild(context.TODO(), spec, diffPath)
	if err != nil {
		t.Error("Load:", err)
	}

	loadInspect, _, err := engine.client.ImageInspectWithRaw(context.TODO(), imageName)
	if err != nil {
		t.Error("Load inspect:", err)
	}
	//t.Log(prebuildInspect)
	//t.Log(loadInspect)
	if prebuildInspect.ID != loadInspect.ID {
		t.Error("Prebuild and Load IDs are different")
	}
}
