# Dependabot control plane

> One Dependabot behaviour for every Simtabi-owned account: a reconciler that keeps each repository's `.github/dependabot.yml` on the standard, and a merge gate that lands only the Dependabot pull requests the policy allows and CI has proven.

Both tools are dry runs unless told otherwise, and neither ever pushes to a default branch.

## What each piece does

| Piece | Job |
|---|---|
| `policy.json` | The single source of every value below. Read by both scripts and by the generator. |
| `reconcile.py` | For one account, lists active repositories, shallow-clones each default branch, runs the shared generator (`simtabi/agent-kit` `skills/repo-conform/scripts/dependabot.py check --strict --policy`), and where it reports drift opens or refreshes one pull request, "Adopt the Dependabot standard", from `chore/dependabot-standard`. |
| `merge.py` | For one account, finds open pull requests by `dependabot[bot]`, decides each with the pure function `decide()`, and with `--apply` merges eligible ones with `gh pr merge --squash --match-head-commit <sha>`. |
| `common.py` | Policy loading and validation, the `gh` wrapper, repository listing and the active filter, summary output. |
| `.github/workflows/dependabot-reconcile.yml` | Monday 14:00 UTC (after Dependabot's own 06:00 America/New_York run) and on demand, one job per org. |
| `.github/workflows/dependabot-merge.yml` | Weekly, Tuesday 14:17 UTC, and on demand, one org at a time, never two runs at once. Skips with a notice while the merge app's credentials are not configured. |
| `.github/workflows/ci.yml` | Unit tests and actionlint on every pull request to this repository. |

Every run prints a table and appends it to the job summary: for the reconciler `repo · status · note`, for the merge gate `repo · PR · action · reason`.

## Policy values

| Key | Value | Meaning |
|---|---|---|
| `version` | `1` | Named in the header of every generated file. Bump it when the rendered shape changes. |
| `accounts.orgs` | 12 owned orgs | Reconciled and merge-gated by the workflows, with a Refresh Bot token per org. |
| `accounts.users` | `imanimanyara` | Not covered by the GitHub App; run locally (below). |
| `exclude` | `[{"repo": "owner/name", "reason": "..."}]` | Repositories neither script touches. A reason is required. |
| `schedule` | weekly, Monday 06:00, America/New_York | The documented convention. |
| `cooldown` | 3 days, 7 for majors | A release is not proposed the day it ships. |
| `open-pull-requests-limit` | `10` | Per ecosystem entry. |
| `labels` | `["dependencies"]` | Applied to every Dependabot pull request. |
| `commit-message-prefix` | per ecosystem | `chore(actions)`, `deps(composer)`, `deps(npm)`, … |
| `groups` | `{ecosystem}-minor-and-patch`, minor + patch | One grouped pull request per ecosystem; majors stay one each. |
| `merge.default` | `actions` | `off`, `actions`, `patch` or `minor`; see below. |
| `merge.overrides` | `{}` | `"owner/repo"` or `"owner/*"` → a merge level. |
| `merge.hold-label` | `automerge:hold` | A pull request carrying it is never merged by the gate. |
| `merge.majors` | `never` | Fixed. Majors are never merged automatically, whatever the level. |
| `local-block` | `# >>> local (kept by the generator)` … `# <<< local` | Repository-specific entries the generator keeps verbatim at the end of `updates:`. |

Client accounts (`adelsaiq`, `dannielagumo`, `joemanch`) are refused by both scripts even if one is added to `accounts` by mistake: `load_policy()` raises.

## Merge rules

`decide(pr, checks, statuses, floor, policy)` returns `(merge, reason)`, first failing rule wins:

1. Not a draft, and no `automerge:hold` label.
2. The update type is known and allowed. The ecosystem comes from the branch (`dependabot/github_actions/…` is `github-actions`). A group pull request counts as minor only when its group is the policy's `<ecosystem>-minor-and-patch`; any other group name is not trusted. A single update is classified from "from X to Y" in the title by semver; under 1.0 a minor bump counts as major. Pre-releases, SHAs and anything else unparseable are not allowed.
3. Levels: `off` allows nothing; `actions` allows non-major GitHub Actions updates; `patch` adds other ecosystems' patches; `minor` adds their minors. Majors never. Override precedence is `owner/repo`, then `owner/*`, then `default`.
4. Every check run on the head SHA has completed with `success`, `neutral` or `skipped`, and every commit status is `success`. Anything pending holds.
5. At least as many check runs as the floor: the count on the head of the repository's most recently merged pull request not authored by Dependabot. With no such pull request the floor is 1 and one check name must look like a test (`test`, `pest`, `phpunit`, `pytest`, `jest`, `vitest`, `spec`).
6. `mergeable_state` is `clean`. GitHub computes it lazily, so a first read of `unknown` holds until the next run.

A workflow that is path-filtered off a Dependabot pull request lowers its check count below the floor, and the pull request is held for a person. That is the intended failure direction.

## Overriding per repository

Add an entry to `merge.overrides` in a pull request to this repository:

```json
"overrides": {
  "laranail/emojis": "patch",
  "ichava/*": "minor",
  "laranail/package-tools": "off"
}
```

To keep a repository-specific Dependabot entry (an extra directory, an `ignore`, a registry), put it inside the local block of that repository's `dependabot.yml`. To stop one pull request from merging, add the `automerge:hold` label. To take a repository out entirely, add it to `exclude` with a reason.

## Credentials

| Workflow | App | Where its key lives | Permissions |
|---|---|---|---|
| reconcile | Refresh Bot | org secret `REFRESH_APP_PRIVATE_KEY`, variable `REFRESH_APP_CLIENT_ID` (every owned org) | contents, pull requests (write) |
| merge | Dependency Merge Bot | repository secret `MERGE_APP_PRIVATE_KEY`, variable `MERGE_APP_CLIENT_ID` on `simtabi/.github` only | contents, pull requests, workflows (write); checks, statuses (read) |

The merge gate gets its own app because it needs `workflows: write`, and Refresh Bot's key is readable by
every public repository's workflows. Create it with `imanimanyara/github-apps`
(`docs/merge-bot.md`): `CLIENT_ID_VAR=MERGE_APP_CLIENT_ID PRIVATE_KEY_SECRET=MERGE_APP_PRIVATE_KEY bin/create-app manifests/merge-bot.json simtabi/.github`,
then install it on every org in `accounts.orgs`.

## Going live

Both workflows ship as dry runs.

| Step | How |
|---|---|
| Try one run | Actions → the workflow → Run workflow, with `apply` ticked. |
| Reconciler on schedule | Set the repository variable `DEPENDABOT_RECONCILE_APPLY` to `true`. |
| Merge gate on schedule | Set the repository variable `DEPENDABOT_MERGE_APPLY` to `true`. |
| Back to dry run | Delete the variable or set it to anything else. |

**Prerequisite for the merge gate:** Refresh Bot's manifest grants `contents` and `pull_requests` only. The gate also needs **checks: read**, **statuses: read** and **workflows: write** (merging an Actions update changes `.github/workflows/`, which GitHub refuses an App without it). Until the App is granted those and each org approves the new permissions, the token step fails rather than the gate running half-blind. While `MERGE_APP_CLIENT_ID` or `MERGE_APP_PRIVATE_KEY` is not set at all, the gate posts a notice and skips its merge jobs instead. The reconciler needs nothing beyond the current two.

## The personal account

The GitHub App is not installed on `imanimanyara`, so run both locally with the personal login, from this repository's root:

```bash
GH_TOKEN=$(gh auth token) python3 dependabot/reconcile.py --owner imanimanyara \
  --generator ~/Artisan/projects/opensource/simtabi/packages/agent-kit
GH_TOKEN=$(gh auth token) python3 dependabot/merge.py --owner imanimanyara
```

Add `--apply` only after reading the dry-run table. Assert the login first: `[ "$(gh api user --jq .login)" = imanimanyara ]`. The `--repo <name>` flag limits the reconciler to named repositories.

## Safety notes

- **No default-branch push.** The reconciler's refspec is `HEAD:refs/heads/chore/dependabot-standard`, with `--force-with-lease` against the branch head it read, so a commit someone else added is never overwritten. A pull request with more than one commit is skipped.
- **A closed pull request is a decision.** If the branch exists with no open pull request, the repository is reported as `skipped:branch-without-open-pr` and nothing is re-proposed until the branch is deleted.
- **Identical content is not re-pushed.** An open pull request whose files already match is reported as `skipped:pr-up-to-date`.
- **Generator exit 2 is a broken input, not a clean repository**, and is reported as skipped.
- **Merges are pinned** with `--match-head-commit`, so a push after the decision fails the merge.
- **The token never lands on disk.** git reads `GH_TOKEN` through a credential helper at run time.
- **Errors are per repository or per pull request.** One failure is reported and the run continues; the exit status is non-zero only when something errored.
- **No `pull_request_target`.** Every workflow starts from `permissions: {}` and grants per job; the App tokens carry only the permissions named in each step.

## Tests

```bash
python3 -m unittest discover -s dependabot/tests -v
```

No network: `gh`, `git` and the generator are replaced with fakes.
