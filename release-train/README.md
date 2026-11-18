# Release train

> Simtabi releases once a week, on Tuesday: merges until Friday 18:00, review Saturday to Monday on a release candidate, and the reviewed commit becomes the release.

The process and its reasons are DEC-044 in company-os-internal (`docs/delivery/processes/release-train.md`). This directory is its automation.

## The week (America/New_York)

| When | Step | What it does |
|---|---|---|
| Fri 18:07 | `cut` | Opens "Release X.Y.Z" from `release/train-X.Y.Z` in each enrolled repository with entries under `[Unreleased]`, moving them to `## [X.Y.Z] - <Tuesday>` |
| Sat to Mon, hourly at :37 | `tag` | Tags `vX.Y.Z-rc.1` on the merged release pull request's commit, then `rc.N+1` on `main` when every commit since the last rc came from a `release-fix` pull request |
| Tue 10:17, retry 12:17 | `promote` | Tags `vX.Y.Z` on the last rc's commit, once an owner has labelled the release pull request `release:approved` and that rc's GitHub release is published |

Each tag starts the repository's own `release.yml` (for Go, the shared `go-release.yml`), which builds, tests and publishes it. A release pull request not merged by Saturday 12:00 misses the train; one merged but not released holds the next cut until it ships.

The version comes from the `[Unreleased]` headings. From 1.0: `Removed`, `Breaking` or `BREAKING` in the text is a major, `Added`, `Changed` or `Deprecated` a minor, `Fixed` or `Security` a patch. Before 1.0 a breaking change is a minor and anything else a patch.

## Joining the train

1. List the repository in [`train.json`](train.json).
2. Make sure its `release.yml` triggers on pre-release tags too (`v*.*.*` and `v*.*.*-*`).
3. Call the freeze check on every pull request:

   ```yaml
   name: Release window
   on:
     pull_request:
       types: [opened, synchronize, reopened, labeled, unlabeled]
     schedule:
       - cron: "47 12 * * 2"
         timezone: America/New_York
   permissions: {}
   jobs:
     window:
       if: github.event_name == 'pull_request'
       uses: simtabi/.github/.github/workflows/release-window.yml@<commit>  # vX.Y.Z
     reopen:
       if: github.event_name == 'schedule'
       permissions:
         actions: write
         pull-requests: read
       uses: simtabi/.github/.github/workflows/release-window.yml@<commit>  # vX.Y.Z
       with:
         mode: reopen
   ```

   On a public repository make `release window` a required check. On Tuesday at 12:47, after the freeze lifts, the `reopen` job re-runs the check on every open pull request it failed, so nothing stays blocked by a freeze that has ended. Only that job holds `actions: write`, and only the repository's own `GITHUB_TOKEN`.

4. Create the labels `release-fix` and `release:approved`.

## Switches and credentials

- **Dry run until switched on.** Scheduled runs write only when the repository variable `RELEASE_TRAIN_APPLY` is `true`; a manual run writes when `apply` is ticked. A dry run prints what each repository would get.
- **Token.** `bot/policy.json`'s `release-train` job: contents write (release branch, CHANGELOG commit, tags) and pull requests write (the release pull request and its labels). A tag pushed with `GITHUB_TOKEN` would start no release workflow.
- **Approval.** Only a login in `train.json`'s `owners` can approve, by adding `release:approved`; the step reads who added it from the pull request's events.
- **Skipped Tuesdays.** `train.json`'s `skip` lists Tuesdays the train does not run; `promote` waits for the next one.

## Testing

```bash
python3 -m unittest discover -s release-train/tests -v
python3 release-train/train.py cut --owner laranail      # dry run against GitHub, with GH_TOKEN set
```

The tests drive each step through a fake GitHub that answers only the calls `train.py` makes, and run the freeze check's own shell against a fixed clock.
