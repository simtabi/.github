# Changelog

Releases of simtabi/.github's shared workflows. Tags are final: a change ships as the next version,
and callers pin `go-release.yml@<commit>  # vX.Y.Z`.

## [Unreleased]

### Changed

- `dependabot/policy.json` reconciles and merge-gates `sangehq`, the eleventh owned org, which was
  missing from `accounts.orgs`. It excludes the three repositories on the WIP ignore list
  (`brandgulp/brandgulp.com`, `simbi-prjs-int/creamer.simtabi.com`, `tusente/web-app`) so turning
  the reconciler on opens no pull request against them.

## [0.1.0] - 2026-11-14

First tagged release of the shared workflows. It replaces `v1.0.0` and `v1.0.1`, withdrawn on
2026-11-14 in a planned history reset; a caller pinned to either moves to this version.

- `.github/workflows/go-release.yml`: the reusable Go release pipeline every Go project's
  `release.yml` calls. It publishes on the repository's GitHub release only, on a pushed `vX.Y.Z` tag
  or on request. Inputs: `tag`, `goreleaser-config`, `go-version-file`, `module-alias-prefix`,
  `changelog`, `post-release`, `runs-on`, `environment`, `node-version` (default: latest), and the
  optional `SIGNPATH_API_TOKEN` secret.
- The release job sets `GOPRIVATE` and `GONOSUMDB` to every Simtabi-owned org, so a release fetches
  our own modules from git and never through proxy.golang.org (finding R-INC-13 from the
  `sangehq/authama` review). `go-release/tests/` pins the list.
- `templates/go/release.yml`: the caller to copy.

[Unreleased]: https://github.com/simtabi/.github/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/simtabi/.github/releases/tag/v0.1.0
