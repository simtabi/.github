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

## Adding a job

1. Add it to `policy.json` with a `why`, its owners, its permissions and, where it can, its repositories.
2. Call `bot-token` with that `job:` from a workflow in this repository, in a job with
   `environment: simtabi-bot`.
3. `python3 -m unittest discover -s bot/tests -v`. A workflow naming a job the policy lacks fails the tests,
   so a rename cannot wait for its schedule to find out.

## Until the app exists

The merge gate posts a notice and skips while `SIMTABI_BOT_CLIENT_ID` or `SIMTABI_BOT_PRIVATE_KEY` is missing
from the environment. The reconciler uses Refresh Bot's `REFRESH_APP_*` until `SIMTABI_BOT_CLIENT_ID` is set,
choosing both halves of the pair on that one condition. The first workflow run that names the environment
creates it with no branch rule; the owner's setup (`github-apps` `docs/simtabi-bot.md`, "Creating it") then
restricts it to `main`.

## Tests

```bash
python3 -m unittest discover -s bot/tests -v
```
