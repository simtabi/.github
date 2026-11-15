# Changelog

Releases of simtabi/.github's shared workflows. Tags are final: a change ships as the next version,
and callers pin `go-release.yml@<commit>  # vX.Y.Z`.

## [Unreleased]

## [0.1.1] - 2026-11-15

### Fixed

- `go-release.yml` publishes a CHANGELOG section longer than a GitHub release allows (125,000
  characters) up to the last whole line that fits, then links the full section in the CHANGELOG at
  the tag. It used to send it whole: GitHub cut the body, the notes check failed and the run stopped
  before attesting provenance (`sangehq/authama` v0.1.0, 157,941 bytes, 2026-11-15). The check now
  compares the notes sent. `go-release/tests` runs the step's own script against a long section.

### Changed

- `templates/health/orgs.json` renders the health set for six more owned orgs: `sangehq`,
  `simsange`, `tayariai`, `tusente`, `simbi-prjs-clt` and `simbi-prjs-int`, each with the
  default entry `new-org-profile.sh` scaffolds, so `render-health.sh --check` covers them.
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

[Unreleased]: https://github.com/simtabi/.github/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/simtabi/.github/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/simtabi/.github/releases/tag/v0.1.0
