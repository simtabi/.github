"""Shared plumbing for the Dependabot control plane: policy, the `gh` runner, repo listing, output.

Standard library only. Every GitHub call goes through a `Gh` instance, so the tests replace it
with a fake and never touch the network.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_POLICY = os.path.join(HERE, "policy.json")

# Client-owned accounts. Simtabi builds them and owns none of them, so nothing here may act on
# them even if a policy edit lists one by mistake.
CLIENT_ACCOUNTS = frozenset({"adelsaiq", "dannielagumo", "joemanch"})

MERGE_LEVELS = ("off", "actions", "patch", "minor")


class GhError(RuntimeError):
    pass


def load_policy(path=DEFAULT_POLICY):
    with open(path, encoding="utf-8") as fh:
        policy = json.load(fh)
    if policy.get("version") != 1:
        raise ValueError(f"{path}: unsupported policy version {policy.get('version')!r}")
    bad = CLIENT_ACCOUNTS & set(policy["accounts"]["orgs"] + policy["accounts"]["users"])
    if bad:
        raise ValueError(f"{path}: client accounts must never be managed: {sorted(bad)}")
    for value in [policy["merge"]["default"], *policy["merge"]["overrides"].values()]:
        if value not in MERGE_LEVELS:
            raise ValueError(f"{path}: merge level {value!r} is not one of {MERGE_LEVELS}")
    return policy


def account_kind(policy, owner):
    """'org' or 'user' for an account the policy manages; ValueError otherwise."""
    if owner in CLIENT_ACCOUNTS:
        raise ValueError(f"{owner} is a client account and is never managed")
    if owner in policy["accounts"]["orgs"]:
        return "org"
    if owner in policy["accounts"]["users"]:
        return "user"
    raise ValueError(f"{owner} is not listed in the policy's accounts")


class Gh:
    """Thin wrapper over the `gh` CLI. GH_TOKEN comes from the environment."""

    def run(self, args, input_text=None, check=True):
        r = subprocess.run(["gh", *args], capture_output=True, text=True, input=input_text)
        if check and r.returncode != 0:
            raise GhError(f"gh {' '.join(args[:3])}: {r.stderr.strip() or r.stdout.strip()}")
        return r

    def api(self, path, paginate=False):
        """Parsed JSON. With paginate, list pages are flattened into one list; object pages
        (check-runs, search) are returned as a list of pages for the caller to flatten."""
        args = ["api", "-H", "Accept: application/vnd.github+json", path]
        if paginate:
            args[1:1] = ["--paginate", "--slurp"]
        out = self.run(args).stdout
        data = json.loads(out or "null")
        if paginate and isinstance(data, list) and all(isinstance(p, list) for p in data):
            return [item for page in data for item in page]
        return data


def list_repos(gh, owner, kind):
    """Every repository of the account, as the API returns them."""
    if kind == "org":
        return gh.api(f"orgs/{owner}/repos?type=all&per_page=100", paginate=True)
    # A user's private repos are only listed for that user's own token.
    me = gh.api("user") or {}
    if me.get("login") == owner:
        return gh.api("user/repos?affiliation=owner&per_page=100", paginate=True)
    return gh.api(f"users/{owner}/repos?type=owner&per_page=100", paginate=True)


def is_empty(gh, repo):
    """No commits. `size` is 0 for an empty repo but also for some tiny ones, so confirm."""
    if repo.get("size", 1) != 0:
        return False
    branches = gh.api(f"repos/{repo['full_name']}/branches?per_page=1")
    return not branches


def active_repos(gh, policy, repos):
    """(active, skipped) where skipped is [(full_name, reason)], per the contract:
    not archived, not empty, not a fork, not in exclude."""
    excluded = {e["repo"].lower(): e.get("reason", "") for e in policy.get("exclude", [])}
    active, skipped = [], []
    for repo in sorted(repos, key=lambda r: r["full_name"].lower()):
        name = repo["full_name"]
        if name.lower() in excluded:
            skipped.append((name, f"excluded: {excluded[name.lower()] or 'policy'}"))
        elif repo.get("archived"):
            skipped.append((name, "archived"))
        elif repo.get("fork"):
            skipped.append((name, "fork"))
        elif is_empty(gh, repo):
            skipped.append((name, "empty"))
        else:
            active.append(repo)
    return active, skipped


def markdown_table(headers, rows):
    def cell(v):
        return str(v).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def write_summary(text):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
