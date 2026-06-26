package components

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
)

// Repeatedly forcing an install of an unchanged artifact must not re-transfer the
// body -- the conditional request is answered with 304. This is the core guarantee
// that prevents the runaway re-download loop.
func TestDownloadFileSkipsUnchangedUnderForce(t *testing.T) {
	const body = "runner-binary-v1"
	const etag = `"v1"`
	var bodyServed int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("If-None-Match") == etag {
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", etag)
		bodyServed++
		_, _ = io.WriteString(w, body)
	}))
	defer srv.Close()

	path := filepath.Join(t.TempDir(), "dstack-runner")

	for i := 0; i < 5; i++ {
		if err := downloadFile(context.Background(), srv.URL, path, 0o755, true); err != nil {
			t.Fatalf("attempt %d: downloadFile: %v", i, err)
		}
	}

	if bodyServed != 1 {
		t.Fatalf("body served %d times; want 1 (forced re-installs must not re-transfer unchanged bytes)", bodyServed)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read installed file: %v", err)
	}
	if string(got) != body {
		t.Fatalf("installed content = %q; want %q", got, body)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o755 {
		t.Fatalf("installed mode = %v; want 0755", info.Mode().Perm())
	}
}

// When the artifact actually changes (different ETag), it must be re-downloaded and
// path updated.
func TestDownloadFileRedownloadsWhenChanged(t *testing.T) {
	bodies := []string{"v1-bytes", "v2-bytes-longer"}
	etags := []string{`"v1"`, `"v2"`}
	cur := 0
	var bodyServed int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("If-None-Match") == etags[cur] {
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", etags[cur])
		bodyServed++
		_, _ = io.WriteString(w, bodies[cur])
	}))
	defer srv.Close()

	path := filepath.Join(t.TempDir(), "dstack-runner")

	if err := downloadFile(context.Background(), srv.URL, path, 0o755, true); err != nil {
		t.Fatal(err)
	}
	cur = 1 // artifact changes upstream
	if err := downloadFile(context.Background(), srv.URL, path, 0o755, true); err != nil {
		t.Fatal(err)
	}
	if bodyServed != 2 {
		t.Fatalf("body served %d times; want 2 (a changed artifact must be re-downloaded)", bodyServed)
	}
	got, _ := os.ReadFile(path)
	if string(got) != bodies[1] {
		t.Fatalf("installed content = %q; want %q", got, bodies[1])
	}
}

// Without force, an already-installed file is left untouched and no request is made
// (preserves prior behavior).
func TestDownloadFileSkipsWithoutForce(t *testing.T) {
	var requests int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		w.Header().Set("ETag", `"x"`)
		_, _ = io.WriteString(w, "x")
	}))
	defer srv.Close()

	path := filepath.Join(t.TempDir(), "dstack-runner")
	if err := os.WriteFile(path, []byte("preexisting"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := downloadFile(context.Background(), srv.URL, path, 0o755, false); err != nil {
		t.Fatal(err)
	}
	if requests != 0 {
		t.Fatalf("made %d requests; want 0 (existing file without force must not hit the network)", requests)
	}
}

// Force-installing two different versions in turn (e.g. two servers expecting
// different versions) must download each version once, then 304 -- not re-download on
// every swap.
func TestDownloadFileFlipFlopDownloadsEachVersionOnce(t *testing.T) {
	var served23, served18 atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body, etag string
		switch r.URL.Path {
		case "/0.20.23/runner":
			body, etag = "RUNNER-0.20.23", `"e23"`
		case "/0.20.18/runner":
			body, etag = "RUNNER-0.20.18-x", `"e18"` // intentionally different length
		default:
			w.WriteHeader(http.StatusNotFound)
			return
		}
		if r.Header.Get("If-None-Match") == etag {
			w.WriteHeader(http.StatusNotModified)
			return
		}
		w.Header().Set("ETag", etag)
		if r.URL.Path == "/0.20.23/runner" {
			served23.Add(1)
		} else {
			served18.Add(1)
		}
		_, _ = io.WriteString(w, body)
	}))
	defer srv.Close()

	path := filepath.Join(t.TempDir(), "dstack-runner")
	url23 := srv.URL + "/0.20.23/runner"
	url18 := srv.URL + "/0.20.18/runner"

	for _, u := range []string{url23, url18, url23, url18, url23, url18} {
		if err := downloadFile(context.Background(), u, path, 0o755, true); err != nil {
			t.Fatalf("downloadFile(%s): %v", u, err)
		}
	}

	if got := served23.Load(); got != 1 {
		t.Fatalf("0.20.23 body served %d times; want 1 (flip-flop must not re-download)", got)
	}
	if got := served18.Load(); got != 1 {
		t.Fatalf("0.20.18 body served %d times; want 1 (flip-flop must not re-download)", got)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "RUNNER-0.20.18-x" {
		t.Fatalf("installed content = %q; want the last requested version (RUNNER-0.20.18-x)", got)
	}
}
