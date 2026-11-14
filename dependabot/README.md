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
| `.github/workflows/dependabot-merge.yml` | Weekly, Tuesday 14:17 UTC, and on demand, one org at a time, never two runs at once. Skips with a notice while `refresh-bot`'s credentials are not configured. |
| `.github/workflows/ci.yml` | Unit tests and actionlint on every pull request to this repository. |

Every run prints a table and appends it to the job summary: for the reconciler `repo · status · note`, for the merge gate `repo · PR · action · reason`.

## Policy values

| Key | Value | Meaning |
|---|---|---|
| `version` | `1` | Named in the header of every generated file. Bump it when the rendered shape changes. |
| `accounts.orgs` | 10 owned orgs | Reconciled and merge-gated by the workflows, with a `refresh-bot` token per org. |
| `accounts.users` | `imanimanyara` | Not covered by the GitHub App; run locally (below). |
| `exclude` | `[{"repo": "owner/name", "reason": "..."}]` | Repositories neither script touches. A reason is required. |
| `schedule` | weekly, Monday 06:00, America/New_York | The documented convention. |
| `cooldown` | 3 days, 7 for majors | A release is not proposed the day it ships. |
| `open-pull-requests-limit` | `10` | Per ecosystem entry. Dependabot's own cap, not the reconciler's. |
| `max-new-per-run` | `5` | The reconciler's own cap: at most this many **new** pull requests per account per run. A pull request already open is still refreshed past it. `0` removes the limit. |
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

Both workflows run as `refresh-bot`, through `.github/actions/bot-token`, with the permissions
[`bot/policy.json`](../bot/README.md) grants each job:

| Workflow | Policy job | Permissions |
|---|---|---|
| reconcile | `dependabot-reconcile`, plus `agent-kit-read` for the generator | contents, pull requests (write); `agent-kit` contents (read) |
| merge | `dependabot-merge` | contents, pull requests (write); checks, statuses (read) |

The credentials are `REFRESH_APP_CLIENT_ID` (variable) and `REFRESH_APP_PRIVATE_KEY` (secret),
organisation-level on every owned org. The Dependency Merge Bot this section used to describe was never
created, and `simtabi-bot` — which briefly held these two jobs — was retired on 2026-11-03 to keep the estate
to two apps; `bot/README.md` has the measurement that decided which app survived.

## Going live

Both workflows ship as dry runs.

> **The reconciler is rate limited, and that is what makes going live safe.** Measured
> 2026-11-02, before the limit existed: a first apply run would have opened **118 pull
> requests across 256 repositories** -- 64 in laranail, 38 in simtabi, 15 in ichava, 1 in
> simbi-prjs-clt. Against the 773 pull requests in the week of 2026-09-30 that made
> "fewer, fuller PRs" a rule, that is not a switch to flip blind.
>
> `policy.json`'s `max-new-per-run` (5) caps **new** pull requests per account per run, so a
> scheduled week opens at most 5 x the number of accounts with drift and the estate converges
> over a few weeks instead of in one burst. `--max-new N` overrides it; `--max-new 0` removes
> the limit. A repository whose pull request is **already open** is still refreshed past the
> budget -- leaving a stale one open is worse than opening nothing.
>
> The budget is spent at the moment a **new** pull request is decided, not before the work.
> Spending it earlier is cheaper and misreports: a conforming repository came back `deferred`
> with nobody having looked at it, and laranail's summary read 63 deferred when only 64 of its
> 77 active repositories drift at all.
>
> A repository held back reads `deferred:rate-limit`, never `skipped:`, and the summary says
> how many were deferred. That distinction is load-bearing: `skipped` means a decision was
> taken about that repository, and a budget says nothing about it. Without it a capped run
> looks like a clean estate -- which is exactly how the two defects in #15 and #16 hid.

| Step | How |
|---|---|
| Try one run | Actions → the workflow → Run workflow, with `apply` ticked. |
| Reconciler on schedule | Set the repository variable `DEPENDABOT_RECONCILE_APPLY` to `true`. |
| Merge gate on schedule | Set the repository variable `DEPENDABOT_MERGE_APPLY` to `true`. |
| Back to dry run | Delete the variable or set it to anything else. |

> **`accounts.orgs` is maintained by hand and nothing checks it against GitHub.** It carried
> `tayaricms` and `the-omaris` until 2026-10-29, by which point both organisations had been deleted —
> every dispatch spent two matrix jobs on accounts that could not exist. It hid because a deleted org
> and an org the app is not installed on fail at the same step with the same
> `404 … get-a-user-installation-for-the-authenticated-app`, so twelve identical failures looked like
> one cause. No test covers this: the check needs the network, and CI has no credential that can list
> an owner's organisations. Re-derive the roster when orgs change, and compare:
>
> ```bash
> gh api user/orgs --paginate --jq '.[].login' | sort > /tmp/real
> python3 -c 'import json;print("\n".join(sorted(json.load(open("dependabot/policy.json"))["accounts"]["orgs"])))' | comm -23 - /tmp/real
> ```
>
> Anything printed is in the policy and not in your organisations. Note that
> `GET /users/{login}` answers 200 for all three deleted orgs here, so it cannot be used for this —
> `GET /orgs/{login}` and `GET /user/orgs` are the endpoints that tell the truth.

**Prerequisite for the merge gate, met on 2026-11-03:** `refresh-bot` holds **checks: read** and **statuses: read**, because `merge.py` reads `commits/{sha}/check-runs` and `/status`. All 10 orgs approved them, and `bot/policy.json`'s `ceiling` was widened only after that — widening it first makes every run answer 422. The gate is still dry-run: it runs only where `DEPENDABOT_MERGE_APPLY` is `true`, and no repository variable sets it, so it has never merged anything.

The gate also has no **workflows: write**, deliberately: its key is organisation-level, and a `workflows: write` credential within reach of every workflow in the estate would let a release job rewrite the CI that gates it. So a Dependabot pull request that touches `.github/workflows/` — the `github-actions` ecosystem, roughly half the volume — is never merged by this token. Use `@dependabot merge` on those, which Dependabot performs with its own credentials.

## The personal account

`refresh-bot` is not installed on `imanimanyara`, so run both locally with the personal login, from this repository's root:

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
