# simtabi-bot

> Every Simtabi automation runs here, as one GitHub App, `simtabi-bot`, with a token narrowed per job by `policy.json`.

The app is defined in `imanimanyara/github-apps` (`manifests/simtabi-bot.json`, `docs/simtabi-bot.md`). Its
private key exists in one place: the `simtabi-bot` environment of this repository, deployable from `main`
only. No other repository holds it, so no other repository's workflows can mint its tokens.

## How a job gets a token

```yaml
environment: simtabi-bot
steps:
  - uses: actions/checkout@v7
    with:
      persist-credentials: false
  - id: token
    uses: ./.github/actions/bot-token
    with:
      job: dependabot-merge
      owner: laranail
      client-id: ${{ vars.SIMTABI_BOT_CLIENT_ID }}
      private-key: ${{ secrets.SIMTABI_BOT_PRIVATE_KEY }}
```

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
| `dependabot-merge` | `*` | contents, pull requests, workflows (write); checks, statuses (read) | all |
| `dependabot-reconcile` | `*` | contents, pull requests (write) | all |
| `agent-kit-read` | `simtabi` | contents (read) | `agent-kit` |

`ceiling` is the app's own permission set and must match the manifest in `github-apps`. A job that needs a
new permission adds it to the manifest, the ceiling and the job in the same change, and each org approves the
new permission once. The action passes exactly the ceiling's permissions; a test fails if the two differ.

Nothing here can test the ceiling against the manifest, because the manifest is in another repository. It
does not need to: a ceiling that claims a permission the app does not hold makes
`create-github-app-token` answer 422 and the job fails on its first run, and a manifest that holds more than
the ceiling only means the extra is never requested. Both directions are loud or harmless, never a token
wider than the policy. Check the live app against the manifest after any edit with
`gh api apps/simtabi-bot --jq .permissions | bin/create-app --check-permissions manifests/simtabi-bot.json`.

`repositories` narrows a job to named repositories of its owner. It is validated at load time, because
getting it wrong is silent: an empty list resolves to `""`, which the action reads as *every* repository of
the owner. So it must be a non-empty list of bare names — not `owner/name`, which matches nothing — and a
job that narrows repositories must name its owners explicitly rather than using `"*"`, or the same names
would be sent to all twelve orgs.

## Adding a job

1. Add it to `policy.json` with a `why`, its owners, its permissions and, where it can, its repositories.
2. Call `bot-token` with that `job:` from a workflow in this repository, in a job with
   `environment: simtabi-bot`.
3. `python3 -m unittest discover -s bot/tests -v`. A workflow naming a job the policy lacks fails the tests,
   so a rename cannot wait for its schedule to find out.

## Until the app exists

Both workflows post a notice and skip their matrix job rather than failing once per org. The merge gate
skips while `SIMTABI_BOT_CLIENT_ID` or `SIMTABI_BOT_PRIVATE_KEY` is missing. The reconciler uses Refresh
Bot's `REFRESH_APP_*` until `SIMTABI_BOT_CLIENT_ID` is set, choosing both halves of the pair on that one
condition so a client ID is never sent with the other app's key — which makes a *half*-configured bot the
real hazard, and the one its readiness check is written against: a client ID with no key skips with a
notice saying so, instead of twelve identical minting failures. Each run's summary names the app it ran as.

**The first workflow run that names the environment creates it with no branch rule at all**, so every branch
can deploy to it, and the key would sit where a workflow on any branch could read it. That is the state
`simtabi-bot` was found in on 2026-10-28. The owner's setup (`github-apps` `docs/simtabi-bot.md`,
"Creating it") restricts it to `main`, and `bin/create-app` now refuses to store a key in an environment
that has no branch policy rather than checking only that the environment exists.

## Tests

```bash
python3 -m unittest discover -s bot/tests -v
```
