#!/usr/bin/env python3
"""Merge the Dependabot pull requests of one account that the policy allows and CI has proven.

Usage:
  merge.py --owner <account> [--policy PATH] [--apply]

Every open pull request authored by dependabot[bot] gets one decision from `decide()`, a pure
function, and the reason is printed whether or not it merges. Dry run is the default. With
`--apply`, an eligible pull request is merged with

  gh pr merge <n> --squash --match-head-commit <sha>

so a commit pushed after the decision was made makes the merge fail instead of landing unchecked.
Anything not eligible stays open for a person; manual merging is unchanged.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DEPENDABOT = "dependabot[bot]"
OK_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
TEST_LIKE = re.compile(r"test|pest|phpunit|pytest|jest|vitest|spec", re.I)

# Dependabot's branch directory per ecosystem -> the policy's ecosystem name.
BRANCH_ECOSYSTEMS = {
    "github_actions": "github-actions",
    "composer": "composer",
    "npm_and_yarn": "npm",
    "pip": "pip",
    "go_modules": "gomod",
    "cargo": "cargo",
    "docker": "docker",
    "bundler": "bundler",
}
VERSION = re.compile(r"^v?(\d+(?:\.\d+){0,3})$")
FROM_TO = re.compile(r"\bfrom (\S+) to (\S+?)(?:\s|$)")
GROUP = re.compile(r"\bthe (\S+) group\b")


def ecosystem_of(head_ref):
    parts = head_ref.split("/")
    if len(parts) < 3 or parts[0] != "dependabot":
        return None
    return BRANCH_ECOSYSTEMS.get(parts[1])


def semver_change(old, new):
    """'major' | 'minor' | 'patch' | None (unparseable, equal, or a downgrade).

    Pre-releases and anything that is not 1-4 numeric components are unparseable. Under 1.0 a
    minor bump is breaking (semver item 4), so 0.x -> 0.y counts as major.
    """
    a, b = VERSION.match(old), VERSION.match(new)
    if not a or not b:
        return None
    x = [int(p) for p in a.group(1).split(".")] + [0] * 4
    y = [int(p) for p in b.group(1).split(".")] + [0] * 4
    x, y = x[:4], y[:4]
    if y <= x:
        return None
    if y[0] != x[0]:
        return "major"
    if y[1] != x[1]:
        return "major" if x[0] == 0 else "minor"
    return "patch"


def update_type(pr, policy):
    """(ecosystem, 'major'|'minor'|'patch'|None, how)."""
    eco = ecosystem_of(pr["head_ref"])
    title = pr["title"]
    g = GROUP.search(title)
    if g:
        expected = policy["groups"]["name-pattern"].replace("{ecosystem}", eco or "?")
        if eco and g.group(1) == expected:
            return eco, "minor", f"group {expected}"
        return eco, None, f"group {g.group(1)!r} is not the policy group"
    m = FROM_TO.search(title)
    if not m:
        return eco, None, "no 'from X to Y' in the title"
    return eco, semver_change(m.group(1), m.group(2)), f"{m.group(1)} -> {m.group(2)}"


def merge_level(policy, repo):
    overrides = policy["merge"]["overrides"]
    owner = repo.split("/")[0]
    level = overrides.get(repo, overrides.get(f"{owner}/*", policy["merge"]["default"]))
    return level if level in common.MERGE_LEVELS else "off"


def allowed(eco, kind, level):
    if kind is None or kind == "major" or level == "off":
        return False  # majors never, whatever the policy says
    if eco == "github-actions":
        return True  # every level from "actions" up allows non-major Actions updates
    if level == "patch":
        return kind == "patch"
    if level == "minor":
        return kind in ("patch", "minor")
    return False


def decide(pr, checks, statuses, floor, policy):
    """(merge, reason). Pure: no I/O.

    pr: {repo, number, title, head_ref, head_sha, draft, mergeable_state, labels: [str]}
    checks: check runs on the head SHA ({name, status, conclusion}).
    statuses: latest commit status per context on the head SHA ({context, state}).
    floor: check runs on the head of the repo's last merged non-Dependabot PR, or None when
      there is none (then at least one check is required, and one must look like a test).
    """
    if pr.get("draft"):
        return False, "draft"
    hold = policy["merge"]["hold-label"]
    if hold in pr.get("labels", []):
        return False, f"held by label {hold}"

    eco, kind, how = update_type(pr, policy)
    if eco is None:
        return False, f"unknown ecosystem for branch {pr['head_ref']}"
    if kind is None:
        return False, f"update type not recognised ({how})"
    if kind == "major":
        return False, f"major update ({how}); majors are never merged automatically"
    level = merge_level(policy, pr["repo"])
    if not allowed(eco, kind, level):
        return False, f"{eco} {kind} not allowed by merge policy {level!r}"

    pending = [c["name"] for c in checks if c.get("status") != "completed"]
    pending += [s["context"] for s in statuses if s.get("state") == "pending"]
    if pending:
        return False, f"pending: {', '.join(sorted(pending))}"
    failing = [f"{c['name']}={c.get('conclusion')}" for c in checks if c.get("conclusion") not in OK_CONCLUSIONS]
    failing += [f"{s['context']}={s.get('state')}" for s in statuses if s.get("state") != "success"]
    if failing:
        return False, f"failing: {', '.join(sorted(failing))}"

    need = 1 if floor is None else max(floor, 1)
    if len(checks) < need:
        return False, f"{len(checks)} check runs reported, floor is {need}"
    if floor is None and not any(TEST_LIKE.search(c["name"]) for c in checks):
        return False, "no merged non-Dependabot PR to set a floor, and no test-like check"

    if pr.get("mergeable_state") != "clean":
        return False, f"mergeable_state is {pr.get('mergeable_state')!r}"
    return True, f"{eco} {kind} ({how}); {len(checks)} checks green, floor {need}"


# ---- I/O ----------------------------------------------------------------------------------------

def flatten(pages, key):
    if isinstance(pages, dict):
        pages = [pages]
    return [item for page in pages or [] for item in page.get(key, [])]


def check_runs(gh, repo, sha):
    return flatten(gh.api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100", paginate=True), "check_runs")


def commit_statuses(gh, repo, sha):
    return (gh.api(f"repos/{repo}/commits/{sha}/status") or {}).get("statuses", [])


def floor_for(gh, repo):
    """Check runs on the head of the most recently merged PR not authored by Dependabot."""
    prs = gh.api(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=50") or []
    merged = [p for p in prs if p.get("merged_at") and p["user"]["login"] != DEPENDABOT]
    if not merged:
        return None
    last = max(merged, key=lambda p: p["merged_at"])
    return len(check_runs(gh, repo, last["head"]["sha"]))


def dependabot_prs(gh, owner, kind):
    qualifier = "org" if kind == "org" else "user"
    q = f"{qualifier}:{owner}+is:pr+is:open+author:app/dependabot"
    items = flatten(gh.api(f"search/issues?q={q}&per_page=100", paginate=True), "items")
    for item in items:
        repo = item["repository_url"].split("/repos/", 1)[1]
        yield repo, item["number"]


def main(argv=None, gh=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--owner", required=True)
    ap.add_argument("--policy", default=common.DEFAULT_POLICY)
    ap.add_argument("--apply", action="store_true", help="merge the eligible pull requests")
    opts = ap.parse_args(argv)
    gh = gh or common.Gh()
    policy = common.load_policy(opts.policy)
    kind = common.account_kind(policy, opts.owner)
    excluded = {e["repo"].lower() for e in policy.get("exclude", [])}

    rows, errors, floors = [], 0, {}
    for repo, number in sorted(dependabot_prs(gh, opts.owner, kind)):
        try:
            if repo.lower() in excluded:
                rows.append((repo, number, "skip", "repository excluded by policy"))
                continue
            raw = gh.api(f"repos/{repo}/pulls/{number}")
            pr = {
                "repo": repo, "number": number, "title": raw["title"], "head_ref": raw["head"]["ref"],
                "head_sha": raw["head"]["sha"], "draft": raw.get("draft", False),
                "mergeable_state": raw.get("mergeable_state"),
                "labels": [lb["name"] for lb in raw.get("labels", [])],
            }
            if repo not in floors:
                floors[repo] = floor_for(gh, repo)
            ok, reason = decide(pr, check_runs(gh, repo, pr["head_sha"]),
                                commit_statuses(gh, repo, pr["head_sha"]), floors[repo], policy)
            action = "hold"
            if ok:
                action = "would merge"
                if opts.apply:
                    gh.run(["pr", "merge", str(number), "--repo", repo, "--squash",
                            "--match-head-commit", pr["head_sha"]])
                    action = "merged"
            rows.append((repo, number, action, reason))
        except Exception as exc:  # one PR's failure must not stop the others
            errors += 1
            rows.append((repo, number, "error", str(exc)[:300]))

    mode = "apply" if opts.apply else "dry run"
    text = (f"## Dependabot merge gate: {opts.owner} ({mode})\n\n{len(rows)} open Dependabot pull requests.\n\n"
            + common.markdown_table(["repo", "PR", "action", "reason"], rows))
    print(text)
    common.write_summary(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
