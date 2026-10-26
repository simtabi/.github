# Licence masters

The starting text for a repository's `LICENSE`, one master per licence, so every owned account words its licences the same way.

## Why these are not rendered at org level

`LICENSE` never cascades. It is not in GitHub's community-health set, licence detection reads the repository's own file, and it ships in every dist archive, so every repository keeps its own. These masters are therefore a starting shape for a new repository, like the `*.repo.md.tmpl` files in `../health/`, and `bin/render-health.sh` does not read them. They are copied by hand, or by the repository scaffolder.

## Which master

| Repository | Master | `composer.json` / `package.json` |
|---|---|---|
| Public, open source | `LICENSE.MIT.tmpl` | `"license": "MIT"` |
| Private, or proprietary however visible | `LICENSE.proprietary.tmpl` | `"license": "proprietary"` (Composer) · `"UNLICENSED"` and `"private": true` (npm) |

Private and proprietary are separate facts. A private repository can still be MIT, and a repository that ships code under a licence forbidding redistribution, such as Untitled UI PRO, is proprietary for that reason alone. Pick by what the code is allowed to do, then set the visibility to match.

## The MIT master stays the exact MIT text

Nothing is appended to an MIT `LICENSE`. Licence detection compares the whole file against the MIT text, and an extra section can push it below the match threshold, which shows the repository as "Other" on GitHub and Packagist. Facts that an MIT repository needs to state go elsewhere:

- Third-party artwork and its required attribution go in `ATTRIBUTION.md`, linked from the README.
- The contributor terms go in `CONTRIBUTING.md`.

The copyright line carries no year, matching ichava, where every repository uses `Copyright (c) Simtabi LLC`. The `Copyright (c) 2026 Simtabi LLC` line already in laranail and simtabi is equally valid and is not to be churned.

## Tokens in the proprietary master

`{{TOKEN}}` is a value; `{{#NAME}}{{/NAME}}` is an optional block, empty by default. Fill a block with one of the texts below, or delete the marker.

| Token | Value |
|---|---|
| `{{LICENSING_CONTACT}}` | the account's licensing contact, from the table below |
| `{{#SUBJECT_EXTRA}}` | what else the licence covers, written as a list continuation, e.g. `, design and written content` for a website |
| `{{#RESTRICTIONS}}` | a use restriction, such as the Metronic text below |
| `{{#ICON_ARTWORK}}` | the icon-artwork section, for any repository that ships or displays third-party icons |
| `{{#THIRD_PARTY}}` | named third-party code and its licence, one line each |

### Licensing contacts

| Account | `{{LICENSING_CONTACT}}` |
|---|---|
| every owned account (`ichava`, `laranail`, `simtabi`, `mukoracms`, `imanimanyara`, `brandgulp`) | `imani@simtabi.com` |

Licensing is a maintainer question, so it goes to the maintainer address. `opensource@simtabi.com` is community mail, and the six laranail proprietary licences that name it predate this master; they are correct to leave until they are next edited. Client accounts (`adelsaiq`, `dannielagumo`, `joemanch`) are never given these masters: their licences are the client's.

### `{{#ICON_ARTWORK}}`

```text

Icons are not Simtabi LLC's
---------------------------
The icon artwork this repository ships or displays belongs to its upstream
authors and stays under their own licences. Simtabi LLC claims no authorship
of it. The attribution each licence requires is given in ATTRIBUTION.md of the
icon-set package that ships the icons.
```

A website that displays the icons adds: `The site's licences page gives the same attribution.`

### `{{#RESTRICTIONS}}` for Metronic

```text

Internal and client use only
----------------------------
The Metronic icons in this repository are licensed to Simtabi LLC for its own
internal development and client work. They may not be redistributed, published,
or shown on any public surface, and this repository must remain private.
```

### `{{#THIRD_PARTY}}`, Laravel application

```text
 The Laravel framework and skeleton are MIT, Copyright (c) Taylor Otwell.
```

## Contributors are not licensors

Every licence names Simtabi LLC as the sole licensor. Developers who work on a repository, staff and outside contributors alike, are contributors. The proprietary master says so in the licence itself; an MIT repository says so in its `CONTRIBUTING.md`, under a *Licensing your contribution* section.

> **This is not legal advice.** These texts make legal statements on behalf of Simtabi LLC. The owner may want a lawyer to read them, and in particular to decide whether contributors who are not employees should sign a contributor agreement, since a sentence in a licence file does not by itself transfer anyone's copyright.

---

[← Health files](../../docs/health-files.md)
