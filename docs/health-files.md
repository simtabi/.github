# Health files

How the org-level community health files are rendered from one set of masters, and where a repository's own file takes over.

## What cascades, and how far

GitHub reads `SECURITY.md`, `SUPPORT.md`, `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` from an account's public `.github` repository and shows them on every repository in **that account** that has no file of its own. Four rules decide what a visitor actually sees:

| Rule | Consequence |
|---|---|
| The cascade stays inside one account | `simtabi/.github` reaches simtabi repositories only. laranail, ichava and every other account each need their own `.github` copy |
| A repository's own file replaces the default outright | No merge, no inheritance by section. A repository with its own `SECURITY.md` never shows the org policy |
| `LICENSE` never cascades | It is not in the health-file set, licence detection reads the repository's own file, and it ships in every dist archive. Every repository keeps its own |
| `CHANGELOG.md` never cascades | It is a record of one repository's releases. There is no org default and never will be |

A private repository inherits from a public `.github` like any other. A single edit to an org file can therefore change the instructions on dozens of repositories at once: state which ones before editing.

## Org files and thin repository files

Each health file is either boilerplate or prose, decided by measuring rather than by filename: blank the package name, normalise whitespace, hash, and count the distinct results.

- **Org level** — the four files in each account's `.github`, rendered from the masters in `templates/health/`. They carry the invariants: the disclosure address, the response targets, the conduct inbox.
- **Repository level, thin** — `CODE_OF_CONDUCT.md` measured as boilerplate, so a repository that keeps one at all keeps the 3-line pointer from `CODE_OF_CONDUCT.repo.md.tmpl`.
- **Repository level, prose** — `SECURITY.md` and `CONTRIBUTING.md` measured as prose. A repository's own copy stays, because it carries facts no other file says. The `*.repo.md.tmpl` files are the starting shape for a new repository, not a target for an existing one.

## The masters

| Master | Renders to | Varies per account |
|---|---|---|
| `SECURITY.md.tmpl` | `<account>/.github/SECURITY.md` | subject, scope, an optional reporting-channel note and an optional closing scope paragraph |
| `SUPPORT.md.tmpl` | `<account>/.github/SUPPORT.md` | the docs pointer, or the whole help section |
| `CONTRIBUTING.md.tmpl` | `<account>/.github/CONTRIBUTING.md` | the heading label |
| `CODE_OF_CONDUCT.md` | `<account>/.github/CODE_OF_CONDUCT.md` | nothing |

Per-account values live in `templates/health/orgs.json`, extracted verbatim from the files they replace, so a bespoke paragraph survives as a value rather than being flattened. An account whose file is its own prose is marked `"keep"` and is never rendered; one that carries no such file by design is `"none"`. The token reference is `templates/health/tokens.md`.

## The security policy

The org security policy is one master for all six owned accounts, ichava included since 2026-10-01. It is email-first: `security@simtabi.com` works for every repository, public or private, and GitHub private vulnerability reporting is named only conditionally, for a public repository whose **Report a vulnerability** button is present.

| Element | Value |
|---|---|
| Acknowledgement | within 5 business days |
| Initial assessment | within 15 business days |
| Status updates | at least every 30 days, and on any material change |
| Resend prompt | after 10 business days without an acknowledgement |
| Coordinated disclosure | 90 calendar days, extensions by mutual agreement (normally up to 30 days), typically 7 days when exploited or already public |
| Safe harbor | adapted from the disclose.io core terms (CC0 1.0); covers only claims Simtabi LLC controls |
| Bounty | none |
| Credit | in the advisory and changelog, with the reporter's permission |

Every time is a target ("aim to"), never a guarantee, and "business days" means Monday to Friday excluding public holidays. The policy closes by saying it is not a contract, a warranty or a service level. Spelling is US throughout (`organization`, `license`, `program`, `authorized`), matching the existing `.github` files, which measured 23 `organization` to 0 `organisation` and 15 `license` to 1 `licence`.

> **This is not legal advice.** The safe-harbor and "about this policy" sections make legal commitments on behalf of Simtabi LLC. The owner may want a lawyer to read the rendered text before it is published.

## Render and check

The renderer and its tests live in the maintainers' private `vcs-orgs-presence` tooling, next to the account checkouts they read. Run from there:

```bash
bin/render-health.sh --check            # diff every owned account against the masters
bin/render-health.sh --org laranail     # one account
bin/render-health.sh --write            # write what differs; never deletes, never touches "keep"
```

`--check` is the default and exits 1 when any rendered file differs from the one on disk, printing a unified diff. It exits 2, rendering nothing, when a token has no value, a value is never used, a client account is named, or fewer than six accounts were inspected — a search that matches nothing must not read as clean.

There is no build step. A rendered file may still be edited by hand; `--check` then reports the edit as drift, and it either moves into `orgs.json` or the master, or the entry becomes `"keep"`.

Run `tests/render-health.sh` after changing the renderer or a master. It works on a temporary copy, asserts that `--check` reports exactly the expected lines outside `SECURITY.md`, that each account's rendered `SECURITY.md` equals the master with its values and still carries its own facts, and runs under both `python3` and the system Python 3.9.

## Advertise a channel only once it is on

GitHub private vulnerability reporting is per repository and off by default. Enable it first, confirm with `gh api repos/{owner}/{repo}/private-vulnerability-reporting --jq .enabled`, and only then name it in a policy. Until then the email address is the whole policy. The repository template's `CHANNELS` token offers the two blocks; pick by what is switched on, never by what is planned.

## Client accounts are excluded

`adelsaiq`, `dannielagumo` and `joemanch` are client-owned. Their disclosure, support and conduct inboxes are AdelsaIQ's own, so they never render from these masters. The renderer refuses them by name, even if `orgs.json` lists one, and the profile audit's check 12 fails any Simtabi address that reaches their files.

## Migration order

1. Land the masters, `orgs.json` and the renderer in `simtabi/.github` through a pull request.
2. Run `--check` against the account checkouts and confirm the diff is only the intended change: `SECURITY.md` on all six accounts (the new policy), the conduct-text repair on `imanimanyara`, and the laranail contributing heading.
3. `--write` one account at a time, each through its own `.github` pull request, and run `bin/health-audit.sh` after each.
4. Point the account scaffolder at the renderer, since block defaults are beyond a `sed` substitution.
5. Replace per-repository `CODE_OF_CONDUCT.md` copies with the 3-line pointer, repository by repository. Leave `SECURITY.md` and `CONTRIBUTING.md` copies where they carry their own prose.


## One security inbox, and how to find it

Security reports go to `security@simtabi.com` and nowhere else. RFC 2142 reserves the `SECURITY`
mailbox name for exactly this. The org SECURITY.md says so in one line: other addresses, such as
`opensource@simtabi.com`, handle community mail, and a report sent there may be delayed. A test
fails if that line disappears.

The website publishes the same contact for tools and researchers at
`https://simtabi.com/.well-known/security.txt`, using the master in
`templates/well-known/security.txt`. RFC 9116 requires `Contact`, and `Expires` exactly once.
Renew `Expires` before it passes, which is 2027-10-01 for the current file, or the file is treated
as stale. `tests/security-txt.py` checks those requirements.
---

[← Docs index](../README.md#documentation)
