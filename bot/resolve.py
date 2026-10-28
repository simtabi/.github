"""Turn a job name and an owner into the narrowed simtabi-bot token request, or refuse.

    python3 bot/resolve.py --job dependabot-merge --owner laranail >> "$GITHUB_OUTPUT"

Prints `permission-<name>=<level>` for every permission the action can pass (empty when the job does
not get it) and `repositories=<a,b>` (empty: every repository of the owner). Exits non-zero, printing
nothing, for a job the policy does not name, an owner it does not allow, or a job with no permissions:
actions/create-github-app-token treats "no permission inputs" as "every permission the app holds".

Standard library only.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "dependabot"))
import common  # noqa: E402  (one list of owned orgs and client accounts, not two)

DEFAULT_POLICY = os.path.join(HERE, "policy.json")
LEVELS = ("read", "write")
RANK = {"read": 1, "write": 2}


def load_policy(path=DEFAULT_POLICY):
    with open(path, encoding="utf-8") as fh:
        policy = json.load(fh)
    if policy.get("version") != 1:
        raise ValueError(f"{path}: unsupported policy version {policy.get('version')!r}")
    ceiling = policy["ceiling"]
    for name, job in policy["jobs"].items():
        perms = job.get("permissions") or {}
        if not perms:
            raise ValueError(f"job {name}: no permissions (the token would inherit the whole app)")
        for perm, level in perms.items():
            if level not in LEVELS:
                raise ValueError(f"job {name}: {perm} level {level!r} is not one of {LEVELS}")
            if perm not in ceiling or RANK[level] > RANK[ceiling[perm]]:
                raise ValueError(f"job {name}: {perm}: {level} exceeds the app's ceiling")
        owners = job.get("owners")
        if owners != "*" and not (isinstance(owners, list) and owners):
            raise ValueError(f"job {name}: owners must be '*' or a non-empty list")
        if isinstance(owners, list) and common.CLIENT_ACCOUNTS & set(owners):
            raise ValueError(f"job {name}: client accounts are never managed")
        if "repositories" in job:
            repos = job["repositories"]
            # An empty list reads as "narrowed" and resolves to "", which the action treats as every
            # repository of the owner -- the exact opposite. Omit the key to mean all.
            if not (isinstance(repos, list) and repos and all(isinstance(r, str) and r for r in repos)):
                raise ValueError(
                    f"job {name}: repositories must be a non-empty list of names, or absent for all")
            if any("/" in r for r in repos):
                raise ValueError(f"job {name}: repositories are names, not owner/name")
            # The same names would otherwise be sent to every managed org, and a repository of that
            # name in another org would be handed a token it was never meant to have.
            if owners == "*":
                raise ValueError(f"job {name}: narrowing repositories needs an explicit owners list")
    return policy


def resolve(policy, managed_orgs, job_name, owner):
    """{'permission-<name>': level-or-'', 'repositories': 'a,b'}; ValueError when refused."""
    job = policy["jobs"].get(job_name)
    if job is None:
        raise ValueError(f"no job {job_name!r} in the bot policy")
    if owner in common.CLIENT_ACCOUNTS:
        raise ValueError(f"{owner} is a client account and is never managed")
    allowed = managed_orgs if job["owners"] == "*" else job["owners"]
    if owner not in allowed:
        raise ValueError(f"job {job_name} may not act on {owner}")
    out = {f"permission-{perm}": job["permissions"].get(perm, "") for perm in policy["ceiling"]}
    out["repositories"] = ",".join(job.get("repositories", []))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--job", required=True)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    args = ap.parse_args(argv)
    try:
        managed = common.load_policy()["accounts"]["orgs"]
        out = resolve(load_policy(args.policy), managed, args.job, args.owner)
    except ValueError as exc:
        print(f"bot-token: {exc}", file=sys.stderr)
        return 1
    for key, value in out.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
