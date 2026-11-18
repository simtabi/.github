"""The weekly release train: cut on Friday, release candidates over the weekend, release on Tuesday.

    python3 release-train/train.py cut     --owner laranail [--apply]
    python3 release-train/train.py tag     --owner laranail [--apply]
    python3 release-train/train.py promote --owner laranail [--apply]

Without --apply nothing is written: each repository's row says what would happen.

cut      For each enrolled repository with entries under CHANGELOG.md's [Unreleased], open a
         "Release X.Y.Z" pull request from release/train-X.Y.Z that moves them under
         "## [X.Y.Z] - <Tuesday>". The version comes from the section's headings.
tag      For each merged release pull request whose version has no final tag: tag vX.Y.Z-rc.1 on
         its merge commit, then vX.Y.Z-rc.N+1 on main's head when every commit since the last rc
         came from a pull request labelled release-fix. Anything else merged during the freeze is
         reported and no rc is tagged.
promote  On a Tuesday not listed in train.json's skip dates, tag vX.Y.Z on the last rc's commit for
         each release pull request an owner labelled release:approved, once that rc's GitHub
         release is published.

Each tag starts the repository's own release.yml, which builds, tests and publishes it. The token
is refresh-bot's, narrowed by bot/policy.json's release-train job; a tag pushed with GITHUB_TOKEN
would start no workflow. The process is company-os-internal docs/delivery/processes/release-train.md
(DEC-044, 18 November 2026).

Standard library only.
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dependabot"))
import common  # noqa: E402  (the gh wrapper, client accounts and summary helpers)

TZ = ZoneInfo("America/New_York")
DEFAULT_CONFIG = os.path.join(HERE, "train.json")
BRANCH_PREFIX = "release/train-"
FIX_LABEL = "release-fix"
APPROVED_LABEL = "release:approved"
CHANGELOG = "CHANGELOG.md"

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")
UNRELEASED = re.compile(r"^## \[Unreleased\][^\n]*\n", re.M)
NEXT_SECTION = re.compile(r"^## \[", re.M)
HEADING = re.compile(r"^### +(.+?)\s*$", re.M)
BREAKING = re.compile(r"\bBREAKING\b")


def load_config(path=DEFAULT_CONFIG):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if cfg.get("version") != 1:
        raise ValueError(f"{path}: unsupported config version {cfg.get('version')!r}")
    if not cfg.get("owners"):
        raise ValueError(f"{path}: no owners, so nothing could ever be approved")
    for repo in cfg.get("repos", []):
        owner = repo.split("/")[0].lower()
        if owner in common.CLIENT_ACCOUNTS:
            raise ValueError(f"{path}: {repo} belongs to a client account")
    for day in cfg.get("skip", []):
        if dt.date.fromisoformat(day).weekday() != 1:
            raise ValueError(f"{path}: skip date {day} is not a Tuesday")
    return cfg


# --- dates ----------------------------------------------------------------------------------------

def train_date(now):
    """The Tuesday a run at `now` (aware) belongs to: the coming Tuesday, or today on a Tuesday."""
    today = now.astimezone(TZ).date()
    return today + dt.timedelta(days=(1 - today.weekday()) % 7)


# --- versions -------------------------------------------------------------------------------------

def parse_tag(name):
    m = TAG.match(name)
    if not m:
        return None
    major, minor, patch, kind, n = m.groups()
    return (int(major), int(minor), int(patch)), kind, int(n) if n else None


def latest_final(tags):
    """The highest vX.Y.Z (no pre-release) among tag names, as a tuple, or None."""
    finals = [p[0] for p in map(parse_tag, tags) if p and p[1] is None]
    return max(finals) if finals else None


def rc_numbers(tags, version):
    """The N of every vX.Y.Z-rc.N tag for `version` (a tuple), ascending."""
    return sorted(p[2] for p in map(parse_tag, tags) if p and p[0] == version and p[1] == "rc")


def fmt(version):
    return ".".join(map(str, version))


def unreleased(text):
    """The body of the [Unreleased] section (may be empty), or None when there is no such section."""
    m = UNRELEASED.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = NEXT_SECTION.search(rest)
    return rest[: nxt.start()] if nxt else rest


def bump(last, section):
    """The next version after `last` (a tuple, or None for a first release) for an [Unreleased] body.

    From 1.0: a breaking change (a "Removed" or "Breaking" heading, or BREAKING in the text) is a
    major, Added/Changed/Deprecated a minor, Fixed/Security a patch. Before 1.0 a breaking change is
    a minor and anything else a patch. None when the section has no entries."""
    if section is None or not re.search(r"^\s*[-*] ", section, re.M):
        return None
    if last is None:
        return (0, 1, 0)
    headings = {h.strip().lower() for h in HEADING.findall(section)}
    breaking = bool(headings & {"removed", "breaking", "breaking changes"}) or bool(BREAKING.search(section))
    major, minor, patch = last
    if major == 0:
        return (0, minor + 1, 0) if breaking else (0, minor, patch + 1)
    if breaking:
        return (major + 1, 0, 0)
    if headings & {"added", "changed", "deprecated"}:
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def cut_changelog(text, version, day, last):
    """CHANGELOG text with [Unreleased]'s entries moved under "## [X.Y.Z] - day", and the compare
    links at the foot moved on when they are there."""
    m = UNRELEASED.search(text)
    if not m:
        raise ValueError("no ## [Unreleased] section")
    new = fmt(version)
    out = text[: m.end()] + f"\n## [{new}] - {day.isoformat()}\n" + text[m.end():]
    link = re.compile(r"^\[Unreleased\]: (\S+)/compare/(\S+)\.\.\.HEAD$", re.M)
    lm = link.search(out)
    if lm and last is not None:
        base, old = lm.group(1), lm.group(2)
        out = out[: lm.start()] + (
            f"[Unreleased]: {base}/compare/v{new}...HEAD\n[{new}]: {base}/compare/{old}...v{new}"
        ) + out[lm.end():]
    return out


# --- GitHub ---------------------------------------------------------------------------------------

class Gh(common.Gh):
    def send(self, method, path, body):
        args = ["api", "-X", method, "-H", "Accept: application/vnd.github+json", path, "--input", "-"]
        out = self.run(args, input_text=json.dumps(body)).stdout
        return json.loads(out or "null")

    def tags(self, repo):
        """{name: commit sha} for every v* tag, annotated tags dereferenced."""
        refs = self.api(f"repos/{repo}/git/matching-refs/tags/v", paginate=True) or []
        out = {}
        for ref in refs:
            name = ref["ref"][len("refs/tags/"):]
            obj = ref["object"]
            sha = obj["sha"]
            if obj["type"] == "tag":
                sha = self.api(f"repos/{repo}/git/tags/{sha}")["object"]["sha"]
            out[name] = sha
        return out

    def file(self, repo, path, ref):
        data = self.api(f"repos/{repo}/contents/{path}?ref={ref}")
        return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

    def release_prs(self, repo):
        prs = self.api(f"repos/{repo}/pulls?state=all&sort=created&direction=desc&per_page=50") or []
        return [p for p in prs if p["head"]["ref"].startswith(BRANCH_PREFIX) and p["base"]["ref"] == p["base"]["repo"]["default_branch"]]

    def head(self, repo, branch):
        return self.api(f"repos/{repo}/git/ref/heads/{branch}")["object"]["sha"]

    def commits_between(self, repo, base, head):
        return self.api(f"repos/{repo}/compare/{base}...{head}")["commits"]

    def commit_prs(self, repo, sha):
        return self.api(f"repos/{repo}/commits/{sha}/pulls") or []

    def labelled_by(self, repo, number, label):
        events = self.api(f"repos/{repo}/issues/{number}/events?per_page=100", paginate=True) or []
        return {e["actor"]["login"] for e in events if e.get("event") == "labeled" and e["label"]["name"] == label}

    def release_published(self, repo, tag):
        r = self.run(["api", f"repos/{repo}/releases/tags/{tag}"], check=False)
        if r.returncode != 0:
            return False
        return not json.loads(r.stdout).get("draft", True)

    def create_tag(self, repo, tag, sha):
        self.send("POST", f"repos/{repo}/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})


def version_of(pr):
    m = re.match(r"^v?(\d+\.\d+\.\d+)$", pr["head"]["ref"][len(BRANCH_PREFIX):])
    return tuple(map(int, m.group(1).split("."))) if m else None


# --- the three steps ------------------------------------------------------------------------------

def cut(gh, repo, now, apply):
    prs = gh.release_prs(repo)
    if any(p["state"] == "open" for p in prs):
        return "skipped:open", "a release pull request is already open"
    tags = gh.tags(repo)
    waiting, waiting_version = current_release(gh, repo, tags)
    if waiting is not None:
        return "skipped:waiting", f"Release {fmt(waiting_version)} is merged and not yet released: {waiting['html_url']}"
    default = gh.api(f"repos/{repo}")["default_branch"]
    text, blob = gh.file(repo, CHANGELOG, default)
    last = latest_final(tags)
    version = bump(last, unreleased(text))
    if version is None:
        return "skipped:nothing", "no entries under [Unreleased]"
    if f"v{fmt(version)}" in tags:
        return "skipped:tagged", f"v{fmt(version)} already exists"
    day = train_date(now)
    branch = f"{BRANCH_PREFIX}{fmt(version)}"
    if not apply:
        return "would-open", f"Release {fmt(version)} for {day}"
    sha = gh.head(repo, default)
    gh.send("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})
    new = cut_changelog(text, version, day, last)
    gh.send("PUT", f"repos/{repo}/contents/{CHANGELOG}", {
        "message": f"Release {fmt(version)}",
        "content": base64.b64encode(new.encode("utf-8")).decode("ascii"),
        "sha": blob, "branch": branch,
    })
    pr = gh.send("POST", f"repos/{repo}/pulls", {
        "title": f"Release {fmt(version)}", "head": branch, "base": default,
        "body": (
            f"## Summary\n\nThe release train for Tuesday {day.isoformat()}: moves `[Unreleased]` to "
            f"`## [{fmt(version)}] - {day.isoformat()}`.\n\n"
            "Merge it by Saturday 12:00 ET to enter the train; merging tags "
            f"`v{fmt(version)}-rc.1`. Until the release, only pull requests labelled `{FIX_LABEL}` merge. "
            f"When the rc is ready, add `{APPROVED_LABEL}` here; Tuesday 10:17 ET tags `v{fmt(version)}`."
        ),
    })
    return "opened", pr["html_url"]


def current_release(gh, repo, tags):
    """The merged release pull request whose version has no final tag yet, or None."""
    for pr in gh.release_prs(repo):
        version = version_of(pr)
        if pr.get("merged_at") and version and f"v{fmt(version)}" not in tags:
            return pr, version
    return None, None


def tag(gh, repo, now, apply):
    tags = gh.tags(repo)
    pr, version = current_release(gh, repo, tags)
    if pr is None:
        return "skipped:none", "no merged release pull request waiting"
    rcs = rc_numbers(tags, version)
    if not rcs:
        name = f"v{fmt(version)}-rc.1"
        if apply:
            gh.create_tag(repo, name, pr["merge_commit_sha"])
        return ("tagged" if apply else "would-tag"), f"{name} on {pr['merge_commit_sha'][:7]}"
    last_name = f"v{fmt(version)}-rc.{rcs[-1]}"
    default = pr["base"]["ref"]
    head = gh.head(repo, default)
    commits = gh.commits_between(repo, tags[last_name], head)
    if not commits:
        return "up-to-date", f"{last_name} is main's head"
    outside = []
    for c in commits:
        prs = gh.commit_prs(repo, c["sha"])
        if not any(FIX_LABEL in {lb["name"] for lb in p.get("labels", [])} for p in prs):
            outside.append(prs[0]["html_url"] if prs else c["sha"][:7])
    if outside:
        return "freeze-breach", "merged without release-fix: " + ", ".join(outside)
    name = f"v{fmt(version)}-rc.{rcs[-1] + 1}"
    if apply:
        gh.create_tag(repo, name, head)
    return ("tagged" if apply else "would-tag"), f"{name} on {head[:7]}"


def promote(gh, repo, now, apply, owners, skip):
    day = now.astimezone(TZ).date()
    if day.weekday() != 1:
        return "skipped:not-tuesday", f"{day} is not a Tuesday"
    if day.isoformat() in skip:
        return "skipped:calendar", f"{day} is a skipped Tuesday (train.json)"
    tags = gh.tags(repo)
    pr, version = current_release(gh, repo, tags)
    if pr is None:
        return "skipped:none", "no merged release pull request waiting"
    rcs = rc_numbers(tags, version)
    if not rcs:
        return "waiting:no-rc", f"no v{fmt(version)}-rc.N yet"
    rc = f"v{fmt(version)}-rc.{rcs[-1]}"
    approvers = gh.labelled_by(repo, pr["number"], APPROVED_LABEL) & set(owners)
    if not approvers:
        return "waiting:approval", f"{pr['html_url']} has no {APPROVED_LABEL} from an owner"
    if not gh.release_published(repo, rc):
        return "waiting:rc-release", f"{rc} has no published GitHub release (its release run failed or is running)"
    name = f"v{fmt(version)}"
    if apply:
        gh.create_tag(repo, name, tags[rc])
    return ("tagged" if apply else "would-tag"), f"{name} on {rc}'s commit {tags[rc][:7]}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["cut", "tag", "promote"])
    ap.add_argument("--owner", required=True, help="Run for this owner's enrolled repositories")
    ap.add_argument("--apply", action="store_true", help="Write: open pull requests and push tags")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.owner.lower() in common.CLIENT_ACCOUNTS:
        raise SystemExit(f"{args.owner} is a client account")
    repos = [r for r in cfg.get("repos", []) if r.split("/")[0].lower() == args.owner.lower()]
    gh, now, rows, failed = Gh(), dt.datetime.now(TZ), [], False
    for repo in repos:
        try:
            if args.step == "cut":
                status, detail = cut(gh, repo, now, args.apply)
            elif args.step == "tag":
                status, detail = tag(gh, repo, now, args.apply)
            else:
                status, detail = promote(gh, repo, now, args.apply, cfg["owners"], set(cfg.get("skip", [])))
        except (common.GhError, KeyError, ValueError) as e:
            status, detail, failed = "error", str(e), True
        failed |= status == "freeze-breach"
        rows.append((repo, status, detail))
        print(f"{repo}\t{status}\t{detail}")
    mode = "applied" if args.apply else "dry run"
    common.write_summary(f"### Release train: {args.step} for {args.owner} ({mode})\n\n"
                         + common.markdown_table(["Repository", "Result", "Detail"], rows))
    if not repos:
        print(f"no repositories enrolled for {args.owner}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
