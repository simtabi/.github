# Changelog

Releases of simtabi/.github's shared workflows. Tags are final: a change ships as the next version,
and callers pin `go-release.yml@<commit>  # vX.Y.Z`.

## [Unreleased]

## [1.0.1] - 2026-11-14

### Fixed

- `go-release.yml` sets `GOPRIVATE` and `GONOSUMDB` to every Simtabi-owned org, not only the
  caller's, so a release fetches our own modules from git and never through proxy.golang.org.
  `sangehq/authama`'s release pulled `github.com/simtabi/go-notifykit/src` through the public proxy
  (finding R-INC-13). `go-release/tests/` pins the list.

## [1.0.0] - 2026-11-13

First tagged release of the shared workflows.

- `.github/workflows/go-release.yml`: the reusable Go release pipeline every Go project's
  `release.yml` calls. It publishes on the repository's GitHub release only, on a pushed `vX.Y.Z` tag
  or on request.
- `templates/go/release.yml`: the caller to copy.

[Unreleased]: https://github.com/simtabi/.github/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/simtabi/.github/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/simtabi/.github/releases/tag/v1.0.0
