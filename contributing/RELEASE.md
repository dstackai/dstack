# Release

This is a `dstack` release guide and checklist for core maintainers.

## Checklist

1. Test `master`:
    1. Compare changes to the previous release, e.g. [`https://github.com/dstackai/dstack/compare/0.19.39...master`](https://github.com/dstackai/dstack/compare/0.19.39...master).
    2. Test that `master` CLI works with the previous server release. PRs that add new model fields can potentially break client backward compatibility.
    3. Test that `master` server works with the previous CLI release.
    4. Pay special attention to releases with DB migrations. Migrations should work with rolling deployments and avoid locking multiple tables. See [MIGRATIONS.md](MIGRATIONS.md).
2. Create a tag, e.g. `git tag 0.19.40`.
3. Push the tag to trigger the Release `workflow`, i.e. `git push --tags`.
4. Generate GitHub release notes from the tag. Highlight major features, deprecations, breaking changes.
5. Install the release build and test once again, e.g. `uv pip install 'dstack[all]==0.19.40' --refresh`.
6. Release `dstack` Sky and `dstack` Enterprise.
7. Publish the release notes and make announcements.

## Troubleshooting

* If a release workflow fails due to a release workflow mistake and the release build is not published, commit a fix and update the tag reference: `git tag -d 0.19.40 && git tag 0.19.40 && git push --tags -f`.
* If a critical bug is found after the release is published, make a new release. In an extreme case, the broken release can be yanked.
