# Go release workflow

`.github/workflows/go-release.yml` is the one release pipeline for every Go project in every
Simtabi-owned org. It builds the binaries and publishes them on the repository's GitHub release, and
nowhere else. The standard it implements is `~/.claude/rules/go.md`, *Go releases* (owner, 2026-11-13).

## Using it

Copy [`templates/go/release.yml`](../templates/go/release.yml) to the repository's
`.github/workflows/release.yml` and pin the `uses:` line to the commit of this repository's latest
`vX.Y.Z` tag, with the version as the comment: `go-release.yml@<commit>  # vX.Y.Z`. It runs on:

- a pushed `vX.Y.Z` or `vX.Y.Z-pre` tag: `git push origin vX.Y.Z`;
- a request naming a tag already on GitHub: `gh workflow run release.yml --repo OWNER/REPO -f tag=vX.Y.Z`.

Push a version tag only for final code: tags are final, and a pushed tag publishes.

## Versions

This repository tags each change to the shared workflow as a release (`v1.0.0` on 2026-11-13 is the
first), and tags are final: a fix gets the next version. A caller pins
the tag's commit with a `# vX.Y.Z` comment, which is the form Dependabot's github-actions updater
recognises: it opens a pull request moving the commit and the comment together when a new tag appears.
A pin to a bare commit, or a comment that names a pull request, is never updated by Dependabot.

## Inputs

| Input | Default | What it is |
|---|---|---|
| `tag` | required | the `vX.Y.Z` tag to build; it must already be on GitHub |
| `goreleaser-config` | `src/.goreleaser.yaml` | the GoReleaser config, from the repository root |
| `go-version-file` | `src/go.mod` | the `go.mod` that pins the Go version |
| `module-alias-prefix` | `src/` | the module's subdirectory, for its `src/vX.Y.Z` alias tag; empty for none |
| `changelog` | `CHANGELOG.md` | its `## [X.Y.Z]` section becomes the release notes |
| `node-version` | `latest` | Node.js for a before-hook that builds a web UI; the latest release unless pinned (`22`) |
| `post-release` | empty | a command run after GoReleaser to attach extra assets; it may write `$RUNNER_TEMP/extra-checksums.txt` to have them attested |
| `runs-on` | `ubuntu-latest` | the runner label for the job; `macos-latest` for a project whose darwin build needs cgo |
| `environment` | empty | a GitHub environment the job runs under (for example `release`); empty for none |

## Secrets

| Secret | Required | What it is |
|---|---|---|
| `SIGNPATH_API_TOKEN` | no | exported to the GoReleaser step for a config that signs through SignPath. Pass it explicitly, `secrets: SIGNPATH_API_TOKEN: ${{ secrets.SIGNPATH_API_TOKEN }}`, never `secrets: inherit` |

## Our own modules come from git

The release job sets `GOPRIVATE` and `GONOSUMDB` to every Simtabi-owned org (`simtabi`, `laranail`,
`ichava`, `sangehq`, `simsange`, `mukoracms`, `brandgulp`, `tayariai`, `tusente`, `simbi-prjs-clt`,
`simbi-prjs-int`), so a release fetches those modules from git and never feeds proxy.golang.org or
sum.golang.org a tag, the same as CI. It covers every org, not only the caller's: `sangehq/authama`
imports `github.com/simtabi/go-notifykit/src`. Client accounts (`adelsaiq`, `dannielagumo`) stay off
the list. The list was re-derived on 2026-11-14 with `gh api user/orgs --jq '.[].login'`; when an org
joins or leaves, change the workflow and `OWNED_ORGS` in `go-release/tests/` together.

Public modules need no credentials over git. The job's `github.token` reaches only the caller's own
repository, so a private module in another repository cannot be fetched by a release build.

## Attestations

Build provenance is attested for `checksums.txt` and any extra assets on a **public** repository
only: GitHub Free refuses attestations on a private one, so both steps skip when
`github.event.repository.private` is true. The release itself still publishes.

This workflow is what signs, not the caller's `release.yml`, so a check of a downloaded asset names
it as the signer:

```bash
gh attestation verify authama_linux_amd64 --repo simtabi/authama \
  --signer-workflow simtabi/.github/.github/workflows/go-release.yml
```

Without `--signer-workflow`, `gh` expects a workflow in the caller's repository and fails with
`Error: verifying with issuer "sigstore.dev"` (measured 2026-11-13 against simtabi/authama v0.1.6,
which verified with the flag). A caller's docs should show the command with it.

## What it refuses

- a tag that is not `vX.Y.Z[-pre]`, or is not on GitHub;
- a GoReleaser config holding any block that publishes elsewhere: `brews`, `homebrew_casks`,
  `scoops`, `winget`, `chocolateys`, `aurs`, `aur_sources`, `snapcrafts`, `flatpaks`, `nix`,
  `dockers`, `dockers_v2`, `docker_manifests`, `docker_signs`, `kos`, `krews`, `npms`,
  `cloudsmiths`, `furies`, `publishers`, `blobs`, `uploads`, `artifactories`;
- a final version with no CHANGELOG section, and a published release whose body is shorter than it.

`go-release/tests/` pins all of this and the template's triggers; CI runs it with actionlint.
