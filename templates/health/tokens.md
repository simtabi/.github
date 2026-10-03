# Health template tokens

The `*.repo.md.tmpl` files render into a single repository. The org-level masters
(`SECURITY.md.tmpl`, `SUPPORT.md.tmpl`, `CONTRIBUTING.md.tmpl` and the canonical `CODE_OF_CONDUCT.md`)
render into `<account>/.github/` through `bin/render-health.py`, with per-account values in `orgs.json`. Nothing here has a build step: substitute the tokens by script or
by hand, then edit freely.

| Token | Value | Example |
|---|---|---|
| `{{ORG}}` | GitHub account slug | `laranail` |
| `{{ORG_LABEL}}` | Display name | `laranail` |
| `{{REPO}}` | Repository slug | `artisan-ui` |
| `{{PACKAGE}}` | Registry name, or the repo slug if unpublished | `laranail/artisan-ui` |
| `{{CONDUCT_CONTACT}}` | Enforcement inbox | `[opensource@simtabi.com](mailto:opensource@simtabi.com)` |
| `{{CHANNELS}}` | One of the two blocks below | |
| `{{SUPPORTED_VERSIONS}}` | One or two sentences | "While the package is pre-1.0, only the latest tag receives security fixes." |
| `{{SCOPE_NOTES}}` | Empty, or a `## Scope notes` section carrying the repo's threat model | artisan-ui's section |
| `{{SETUP}}`, `{{CHECKS}}` | The repo's own commands, in fenced blocks | `composer install`, `composer test` |
| `{{PACKAGE_SECTIONS}}` | Empty, or the repo's bespoke `##` sections, moved verbatim | "The built assets are committed" |

## `{{CHANNELS}}`: pick by what is actually switched on

Never advertise a channel that is off. Check the repo's `/security/policy` page for the "Report a
vulnerability" button before choosing the first block.

Public repository with private vulnerability reporting enabled:

```markdown
- **Preferred:** [GitHub private vulnerability reporting](https://github.com/{{ORG}}/{{REPO}}/security/advisories/new).
- **Fallback:** email **[security@simtabi.com](mailto:security@simtabi.com)**, if you have no GitHub account.
```

Private repository, or reporting not enabled:

```markdown
Email **[security@simtabi.com](mailto:security@simtabi.com)**.
```

Client-owned accounts (`adelsaiq`, `dannielagumo`, `joemanch`) never render from these templates.
They use their own inboxes.

## Org masters

| Master | Tokens | Notes |
|---|---|---|
| `SECURITY.md.tmpl` | `{{SUBJECT}}`, `{{SCOPE}}`, `{{EXTRA}}`; block `CHANNEL_EXTRA` | `{{SUBJECT}}` completes "Simtabi LLC maintains …" and names the account with a link; `{{SCOPE}}` is `in this organization` or `on this account`; `{{EXTRA}}` closes the Scope section and `CHANNEL_EXTRA` follows the private-reporting paragraph, each starting with a blank line when set. Paragraphs are one line each, unwrapped. The fixed text carries the 5 / 15 / 30 business-day targets, 90-day coordinated disclosure, safe harbor and no bounty; it is not legal advice, so have it read before changing those sections |
| `SUPPORT.md.tmpl` | `{{DOCS_EXTRA}}`; blocks `HELP`, `DOCS`, `EXCEPTION_JOIN` | an account with its own support prose replaces the whole `HELP` block |
| `CONTRIBUTING.md.tmpl` | `{{ORG_LABEL}}` | only the heading varies; an account with its own guide is `"keep"` |
| `CODE_OF_CONDUCT.md` | none | Contributor Covenant 2.1, enforcement `opensource@simtabi.com` |

`{{#NAME}}default{{/NAME}}` is a block with a default: the master's text unless the account sets
`NAME`. In `orgs.json`, `"keep"` means the account's own file is the source and is never rendered;
`"none"` means the account carries no such file by design.
