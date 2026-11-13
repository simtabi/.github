# Go release workflow

`.github/workflows/go-release.yml` is the one release pipeline for every Go project in every
Simtabi-owned org. It builds the binaries and publishes them on the repository's GitHub release, and
nowhere else. The standard it implements is `~/.claude/rules/go.md`, *Go releases* (owner, 2026-11-13).

## Using it

Copy [`templates/go/release.yml`](../templates/go/release.yml) to the repository's
`.github/workflows/release.yml` and pin the `uses:` line to a commit of this repository. It runs on:

- a pushed `vX.Y.Z` or `vX.Y.Z-pre` tag: `git push origin vX.Y.Z`;
- a request naming a tag already on GitHub: `gh workflow run release.yml --repo OWNER/REPO -f tag=vX.Y.Z`.

Push a version tag only for final code: tags are final, and a pushed tag publishes.

## Inputs

| Input | Default | What it is |
|---|---|---|
| `tag` | required | the `vX.Y.Z` tag to build; it must already be on GitHub |
| `goreleaser-config` | `src/.goreleaser.yaml` | the GoReleaser config, from the repository root |
| `go-version-file` | `src/go.mod` | the `go.mod` that pins the Go version |
| `module-alias-prefix` | `src/` | the module's subdirectory, for its `src/vX.Y.Z` alias tag; empty for none |
| `changelog` | `CHANGELOG.md` | its `## [X.Y.Z]` section becomes the release notes |
| `post-release` | empty | a command run after GoReleaser to attach extra assets; it may write `$RUNNER_TEMP/extra-checksums.txt` to have them attested |

## What it refuses

- a tag that is not `vX.Y.Z[-pre]`, or is not on GitHub;
- a GoReleaser config holding any block that publishes elsewhere: `brews`, `homebrew_casks`,
  `scoops`, `winget`, `chocolateys`, `aurs`, `aur_sources`, `snapcrafts`, `flatpaks`, `nix`,
  `dockers`, `dockers_v2`, `docker_manifests`, `docker_signs`, `kos`, `krews`, `npms`,
  `cloudsmiths`, `furies`, `publishers`, `blobs`, `uploads`, `artifactories`;
- a final version with no CHANGELOG section, and a published release whose body is shorter than it.

`go-release/tests/` pins all of this and the template's triggers; CI runs it with actionlint.
