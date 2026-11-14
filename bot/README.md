# The CI bot

> Every Simtabi CI automation runs as one GitHub App, `refresh-bot`, with a token narrowed per job by `policy.json`.

**The app changed on 2026-11-03: `simtabi-bot` was retired and `refresh-bot` took its jobs.** The estate is
held to two apps — `simbi-github-cli` for local `gh` and `git`, and this one for CI — and the direction was
decided by measurement rather than by which app was newer:

```
refresh-bot   checks=read contents=write metadata=read
              pull_requests=write statuses=read                      (5, was 3)
simtabi-bot   + checks, issues, statuses, workflows=write             (7)
```

`refresh-bot` is the **narrower** app, and 35 workflow files across the estate already used it against 2 for
`simtabi-bot` — so it was both the safer and the cheaper survivor. Everything in this directory is
app-agnostic: `policy.json`, `resolve.py` and the `bot-token` action take a client ID and a key as inputs, so
only the credentials the workflows pass changed.

Its key is an **organisation-level secret on every owned org**, which is the reach the 35 files need and the
reason the ceiling below must stay exactly what the app holds. The app is defined in
`imanimanyara/github-apps` (`manifests/refresh-bot.json`, `docs/refresh-bot.md`).

## How a job gets a token

```yaml
steps:
  - uses: actions/checkout@v7
    with:
      persist-credentials: false
  - id: token
    uses: ./.github/actions/bot-token
    with:
      job: release-pr
      owner: laranail
      client-id: ${{ vars.REFRESH_APP_CLIENT_ID }}
      private-key: ${{ secrets.REFRESH_APP_PRIVATE_KEY }}
```

On GitHub Free a **private** repository cannot read organisation secrets and needs repository copies of both.

`bot-token` runs `resolve.py`, which looks the job up in `policy.json` and either refuses or hands
`actions/create-github-app-token` exactly that job's permissions and repositories. It refuses:

- a job `policy.json` does not name;
- an owner the job does not list (`"*"` means the orgs in `dependabot/policy.json` `accounts.orgs`);
- a client account (`adelsaiq`, `dannielagumo`, `joemanch`), whatever the policy says;
- a policy whose job has no permissions, or one above the ceiling. A token request with no permission
  inputs at all would carry every permission the app holds, so an empty job is a load error, not a default.

## The policy

| Job | Owners | Permissions | Repositories |
|---|---|---|---|
| `dependabot-merge` | `*` | contents, pull requests (write); checks, statuses (read) | all |
| `dependabot-reconcile` | `*` | contents, pull requests (write) | all |
| `agent-kit-read` | `simtabi` | contents (read) | `agent-kit` |
| `release-pr` | `*` | contents, pull requests (write) | all |
| `estate-read` | `*` | contents, pull requests (read) | all |
| `private-dep-read` | `simtabi` | contents (read) | `sis-sdk`, `docsmith` |
| `consumer-read` | `ichava` | contents (read) | `icon-browser`, `ichava.com` |
| `package-repo-push` | `simtabi` | contents, pull requests (write) | `homebrew-tap`, `scoop-bucket` |

> **`dependabot-merge` can read checks since 2026-11-03.** `merge.py` reads `commits/{sha}/check-runs` and
> `/status`; `refresh-bot` was granted `checks: read` and `statuses: read` that day and all 10 orgs approved
> them, so the ceiling moved with the app rather than ahead of it. It still has **no `workflows: write`**, by
> design: this app's key is organisation-level, and that permission within reach of every workflow in the
> estate would let a release job rewrite the CI that gates it. So a pull request touching `.github/workflows/`
> is never merged by this token — leave those to `@dependabot merge`, which Dependabot performs with its own
> credentials. The gate is still dry-run until `DEPENDABOT_MERGE_APPLY` is set; it has never merged anything.

`ceiling` is the app's own permission set and must match the manifest in `github-apps`. A job that needs a
new permission adds it to the manifest, the ceiling and the job in the same change, and each org approves the
new permission once. The action passes exactly the ceiling's permissions; a test fails if the two differ.

Nothing here can test the ceiling against the manifest, because the manifest is in another repository. It
does not need to: a ceiling that claims a permission the app does not hold makes
`create-github-app-token` answer 422 and the job fails on its first run, and a manifest that holds more than
the ceiling only means the extra is never requested. Both directions are loud or harmless, never a token
wider than the policy. Check the live app against the manifest after any edit with
`gh api apps/refresh-bot --jq .permissions | bin/create-app --check-permissions manifests/refresh-bot.json`.

`repositories` narrows a job to named repositories of its owner. It is validated at load time, because
getting it wrong is silent: an empty list resolves to `""`, which the action reads as *every* repository of
the owner. So it must be a non-empty list of bare names — not `owner/name`, which matches nothing — and a
job that narrows repositories must name its owners explicitly rather than using `"*"`, or the same names
would be sent to all twelve orgs.

## Adding a job

1. Add it to `policy.json` with a `why`, its owners, its permissions and, where it can, its repositories.
2. Call `bot-token` with that `job:` from a workflow, passing `vars.REFRESH_APP_CLIENT_ID` and
   `secrets.REFRESH_APP_PRIVATE_KEY`.
3. `python3 -m unittest discover -s bot/tests -v`. A workflow naming a job the policy lacks fails the tests,
   so a rename cannot wait for its schedule to find out.
4. If the job needs a permission outside the ceiling, **the ceiling does not move on its own.** Grant it on
   the app first, let every org approve it, then widen `ceiling` and `REFRESH_BOT_HELD` in the tests in one
   change. A ceiling claiming a permission the app lacks makes every run 422.

## When a credential is missing

Both workflows post a notice and skip their matrix job rather than failing once per org, and both halves of
the pair are checked together so a client ID is never sent without its key: without that check it is ten
`create-github-app-token` failures instead of one notice. Each run's summary names the app it ran as.

**`REFRESH_APP_CLIENT_ID` and `REFRESH_APP_PRIVATE_KEY` are organisation-level on every owned org.** On
GitHub Free a *private* repository cannot read organisation secrets and needs repository copies of both,
which is why several private repositories carry their own.

> **The retired app's key is still in this repository's `simtabi-bot` environment**, and deleting it is the
> owner's step — see `github-apps` `docs/simtabi-bot.md`. Nothing reads it now: no workflow here names
> `SIMTABI_BOT_*`, which `grep` over this repository confirms. A key nobody reads is still a key nobody
> rotates, so remove the environment when the app is deleted rather than leaving it to age.

## Tests

```bash
python3 -m unittest discover -s bot/tests -v
```
