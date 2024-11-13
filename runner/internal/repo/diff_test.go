package repo

import (
	"context"
	"os"
	"path"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestApplyDiff(t *testing.T) {
	cases := []struct {
		name    string
		diff    string
		exp     string
		expFile string
		expDel  string
		contAdd string
		cont    string
		expMode os.FileMode
	}{
		{
			name: "Simple edit",
			diff: `diff --git a/original b/original
index 4329f74..7c15ed9 100644
--- a/original
+++ b/original
@@ -1,4 +1,5 @@
 First line.
+Insert after first
 Second line.
 Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
 Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
@@ -6,5 +7,3 @@ Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu
 Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
 Line 7.
 Line eight.
-Almost finish.
-Last line.
\ No newline at end of file
`,
			exp: `First line.
Insert after first
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
`,
		},
		{
			name: "Add to the end",
			diff: `diff --git a/original b/original
index 4329f74..15b634d 100644
--- a/original
+++ b/original
@@ -7,4 +7,5 @@ Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deseru
 Line 7.
 Line eight.
 Almost finish.
-Last line.
\ No newline at end of file
+Last line.
+New last line.
\ No newline at end of file`,
			exp: `First line.
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
Almost finish.
Last line.
New last line.`,
		},
		{
			name: "Simple rename",
			diff: `diff --git a/original b/renamed
similarity index 100%
rename from original
rename to renamed`,
			expFile: "renamed",
			expDel:  "original",
		},
		{
			name: "Rename with edit",
			diff: `diff --git a/original b/renamed
similarity index 96%
rename from original
rename to renamed
index 4329f74..e36ba61 100644
--- a/original
+++ b/renamed
@@ -1,3 +1,4 @@
+Zero line.
 First line.
 Second line.
 Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
`,
			expFile: "renamed",
			expDel:  "original",
			exp: `Zero line.
First line.
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
Almost finish.
Last line.`,
		},
		{
			name: "Delete file",
			diff: `diff --git a/original b/original
deleted file mode 100644
index 4329f74..0000000
--- a/original
+++ /dev/null
@@ -1,10 +0,0 @@
-First line.
-Second line.
-Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
-Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
-Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
-Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
-Line 7.
-Line eight.
-Almost finish.
-Last line.
\ No newline at end of file`,
			expDel: "original",
		},
		{
			name: "New file",
			diff: `diff --git a/a/b/c/new.file b/a/b/c/new.file
new file mode 100644
index 0000000..17e075c
--- /dev/null
+++ b/a/b/c/new.file
@@ -0,0 +1,2 @@
+New file created near the original
+with new-line on the end.
`,
			expFile: path.Join("a", "b", "c", "new.file"),
			exp:     "New file created near the original\nwith new-line on the end.\n",
		},
		{
			name: "nobr-nobr",
			diff: `diff --git a/original b/original
index 4329f74..d032255 100644
--- a/original
+++ b/original
@@ -7,4 +7,5 @@ Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deseru
 Line 7.
 Line eight.
 Almost finish.
-Last line.
\ No newline at end of file
+Last line.
+Add no BR
\ No newline at end of file`,
			exp: `First line.
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
Almost finish.
Last line.
Add no BR`,
		},
		{
			name:    "br-br",
			contAdd: "\n",
			diff: `diff --git a/original b/original
index 2b20eab..3283944 100644
--- a/original
+++ b/original
@@ -8,3 +8,4 @@ Line 7.
 Line eight.
 Almost finish.
 Last line.
+Add BR`,
			exp: `First line.
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
Almost finish.
Last line.
Add BR
`,
		},
		{
			name: "Binary",
			cont: "\x00\x01\x02\x03",
			exp:  "\x0A\x0B\x0C",
			diff: `diff --git a/original b/original
index eaf36c1daccfdf325514461cd1a2ffbc139b5464..20fc8b203d3801e7aef99fe1663888719fc20f78 100644
GIT binary patch
literal 3
Kcmd<$<^cczLjWQG

literal 4
LcmZQzWMT#Y01f~L

`,
		},
		{
			name:    "Executable perm",
			expMode: 0100,
			diff:    "diff --git a/original b/original\nold mode 100644\nnew mode 100755\n",
		},
		{
			name: "e2e-micro based",
			diff: "diff --git a/original b/original\nindex 1a003d5..c812cd8 100644\n--- a/original\n+++ b/original\n@@ -1 +1 @@\n-variable.txt Original line\n+variable.txt Changed line\n\\ No newline at end of file",
			cont: "variable.txt Original line\n",
			exp:  "variable.txt Changed line",
		},
		{
			name: "real gpt-2 part",
			cont: `workflows:
  - name: encode-dataset
    image: tensorflow/tensorflow:1.15.0-py3
    commands:
      - curl -O https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
      - pip3 install -r requirements.txt
      - mkdir datasets
      - PYTHONPATH=src ./encode.py --model_name $model input.txt datasets/input.npz
    depends-on:
      repo:
        include:
          - requirements.txt
          - encode.py
          - src/load_dataset.py
          - src/encoder.py
      workflows:
        - download-model
    artifacts:
      - datasets
`,
			diff: `diff --git a/original b/original
index 9ce1261..f9c7821 100644
--- a/original
+++ b/original
@@ -4,7 +4,7 @@ workflows:
     commands:
       - curl -O https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
       - pip3 install -r requirements.txt
-      - mkdir datasets
+      - mkdir -p datasets
       - PYTHONPATH=src ./encode.py --model_name $model input.txt datasets/input.npz
     depends-on:
       repo:`, // real diff from server does not have last CR
			exp: `workflows:
  - name: encode-dataset
    image: tensorflow/tensorflow:1.15.0-py3
    commands:
      - curl -O https://github.com/karpathy/char-rnn/blob/master/data/tinyshakespeare/input.txt
      - pip3 install -r requirements.txt
      - mkdir -p datasets
      - PYTHONPATH=src ./encode.py --model_name $model input.txt datasets/input.npz
    depends-on:
      repo:
        include:
          - requirements.txt
          - encode.py
          - src/load_dataset.py
          - src/encoder.py
      workflows:
        - download-model
    artifacts:
      - datasets
`,
		},
		{
			name: "empty diff check no error",
		},
	}

	content :=
		`First line.
Second line.
Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Line 7.
Line eight.
Almost finish.
Last line.`

	for _, c := range cases {
		cc := c
		t.Run(c.name, func(t *testing.T) {
			dir, err := os.MkdirTemp("", "dstack-unit-")
			assert.NoError(t, err, "create tmp directory for test")
			if err != nil {
				defer func() {
					_ = os.RemoveAll(dir)
				}()
			}
			if t.Failed() {
				return
			}
			t.Logf("tmp directory: %s", dir)
			cont := cc.cont
			if cont == "" {
				cont = content + cc.contAdd
			}
			err = os.WriteFile(path.Join(dir, "original"), []byte(cont), 0o660)
			assert.NoError(t, err, "write original file")
			ctx := context.Background()
			err = ApplyDiff(ctx, dir, cc.diff)
			assert.NoError(t, err, "apply diff returns")
			fn := cc.expFile
			if fn == "" {
				fn = "original"
			}
			if cc.expDel != "" {
				assert.NoFileExists(t, path.Join(dir, cc.expDel), "check file deleted")
			}
			if fn != cc.expDel {
				fn = path.Join(dir, fn)
				buf, err := os.ReadFile(fn)
				assert.NoError(t, err, "read changed file")
				if err == nil {
					exp := cc.exp
					if exp == "" {
						exp = content
					}
					assert.Equal(t, exp, string(buf))
				}
				if cc.expMode != 0 {
					stat, err := os.Stat(fn)
					assert.NoError(t, err, "stat changed file")
					if err == nil {
						assert.NotZero(t, stat.Mode()&cc.expMode, "masked file permission check")
					}
				}
			}
		})
	}
}
