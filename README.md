# simtabi/.github

> Organization-wide community health files for the
> [simtabi](https://github.com/simtabi) organization.

This repository provides the org profile README (`profile/README.md`) and the
default `SECURITY.md`, `SUPPORT.md`, `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md`
that apply to every simtabi repository lacking its own copy.

## <a name="documentation"></a>Documentation

- [Health files](docs/health-files.md) — where each health file lives, why, and how the org copies are rendered from the masters in [`templates/health/`](templates/health/).
- [The CI bot](bot/README.md) — `refresh-bot`, the one automation app: where its key lives, the per-job token policy, adding a job.
- [Dependabot control plane](dependabot/README.md) — the reconciler and the merge gate that run as the bot.
- [Go release workflow](go-release/README.md) — the reusable workflow every Go repository's `release.yml` calls: binaries on the GitHub release only, built on a version tag or on request.

## License

MIT — see individual repositories for their license files.
