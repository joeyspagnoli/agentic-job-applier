# History scrub before going public

`config/resume.tex` previously contained personal data and was committed in
one commit (`1a4e13f` — the .tex-only API rewrite). It is now gitignored, but
the file still exists in git history. Before pushing this repository public,
remove that historical version.

## Steps

```bash
# 1. Install git-filter-repo if you don't have it.
brew install git-filter-repo

# 2. Confirm there is exactly one commit touching the file.
git log --all --oneline -- config/resume.tex

# 3. From a clean clone of this repo, scrub the path from all history.
git filter-repo --path config/resume.tex --invert-paths

# 4. Verify the file no longer appears in any commit.
git log --all --diff-filter=D --summary | grep -F config/resume.tex || echo "clean"

# 5. Force-push to the remote.
git push origin --force --all
git push origin --force --tags
```

`filter-repo` rewrites every commit hash after the deletion point, so any
existing clones (yours included) need to be re-cloned. If you have not yet
pushed this repo public, this is the moment — do the scrub, then push.

After the scrub, delete this file — it is no longer load-bearing.
