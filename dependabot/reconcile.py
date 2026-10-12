#!/usr/bin/env python3
"""Bring every active repository of one account to the Dependabot standard, by pull request.

Usage:
  reconcile.py --owner <account> --generator <agent-kit checkout> [--policy PATH] [--apply]

For each active repository (not archived, not empty, not a fork, not excluded by the policy) it
shallow-clones the default branch and runs the shared generator:

  python3 <agent-kit>/skills/repo-conform/scripts/dependabot.py check <clone> --strict --policy <policy>

Exit 0 conforms. Exit 1 is drift: the generator renders the file with `--write`, and with
`--apply` the result is pushed to `chore/dependabot-standard` and one pull request titled
"Adopt the Dependabot standard" is opened, or refreshed when it is already open. Exit 2 (nothing
inspected) and any other code skip the repository and are reported.

Safety: the default branch is never pushed to; the push names `refs/heads/chore/dependabot-standard`
explicitly and uses a lease, so a commit someone else added to that branch is never overwritten.
An open PR whose content already matches is left alone. A branch that exists with no open PR (a
person closed it) is reported, not re-proposed.

Dry run is the default and makes no GitHub writes. Exit status is non-zero only on errors.
GH_TOKEN comes from the environment; it is handed to git through a credential helper that reads
the variable at run time, so it is never written into a clone's config.
"""
import argparse
import base64
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

BRANCH = "chore/dependabot-standard"
TITLE = "Adopt the Dependabot standard"
GENERATOR = os.path.join("skills", "repo-conform", "scripts", "dependabot.py")
GIT_AUTH = [
    "-c", "credential.helper=",
    "-c", 'credential.helper=!f() { echo username=x-access-token; echo "password=$GH_TOKEN"; }; f',
]


class Shell:
    def run(self, cmd, check=True, input_text=None):
        r = subprocess.run(cmd, capture_output=True, text=True, input=input_text)
        if check and r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd[:4])}: {r.stderr.strip() or r.stdout.strip()}")
        return r


def pr_body(policy, default_branch):
    begin, end = policy["local-block"]["begin"], policy["local-block"]["end"]
    return f"""This brings `.github/dependabot.yml` to the Simtabi Dependabot standard (policy version {policy['version']}).

**What the standard is.** One entry per ecosystem this repository actually has, each with:

- a weekly schedule: {policy['schedule']['day'].title()} {policy['schedule']['time']}, {policy['schedule']['timezone']};
- a `{policy['groups']['name-pattern']}` group, so minor and patch updates arrive as one pull request per ecosystem and majors stay one pull request each;
- a cooldown of {policy['cooldown']['default-days']} days ({policy['cooldown']['semver-major-days']} for majors), so a release is not proposed the day it ships;
- `open-pull-requests-limit: {policy['open-pull-requests-limit']}`, the `dependencies` label and a commit-message prefix per ecosystem.

**The local block.** Anything this repository needs beyond the standard goes between these two lines, at the end of `updates:`:

```yaml
{begin}
{end}
```

The generator keeps that block verbatim on every run. Everything outside it is rendered, so a hand edit there is replaced by the next reconcile.

**How this pull request is maintained.** The reconciler in `simtabi/.github` (`dependabot/reconcile.py`) re-renders the file weekly. While this pull request is open it refreshes this branch only; it never pushes to `{default_branch}`. Close it to decline the change; the branch is then left alone and the repository is reported as skipped until the branch is deleted.

Auto-merge of Dependabot's own pull requests is decided separately by `dependabot/merge.py` in the same repository; see its README for the rules."""


def changed_paths(shell, dest):
    out = shell.run(["git", "-C", dest, "status", "--porcelain", "-z", "--untracked-files=all"]).stdout
    return sorted(entry[3:] for entry in out.split("\0") if len(entry) > 3)


def read_local(dest, path):
    try:
        with open(os.path.join(dest, path), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def read_remote(gh, full_name, path, ref):
    try:
        data = gh.api(f"repos/{full_name}/contents/{path}?ref={ref}")
    except common.GhError:
        return None
    if not isinstance(data, dict) or "content" not in data:
        return None
    return base64.b64decode(data["content"]).decode("utf-8")


def branch_head(gh, full_name):
    try:
        ref = gh.api(f"repos/{full_name}/git/ref/heads/{BRANCH}")
    except common.GhError:
        return None
    return (ref or {}).get("object", {}).get("sha")


def open_pr(gh, full_name, owner):
    prs = gh.api(f"repos/{full_name}/pulls?state=open&head={owner}:{BRANCH}&per_page=10") or []
    if not prs:
        return None
    return gh.api(f"repos/{full_name}/pulls/{prs[0]['number']}")


def reconcile_repo(repo, owner, gh, shell, opts, policy, workdir):
    """(status, note). Raises on errors; the caller records them."""
    name, default = repo["full_name"], repo["default_branch"]
    if not default or default == BRANCH:
        return "skipped:default-branch-is-the-reconciler-branch", ""
    dest = os.path.join(workdir, name.replace("/", "__"))
    url = f"https://github.com/{name}.git"
    shell.run(["git", *GIT_AUTH, "clone", "--quiet", "--depth", "1", "--branch", default, url, dest])

    gen = [sys.executable, opts.generator_script, "check", dest, "--strict", "--policy", opts.policy]
    rc = shell.run(gen, check=False).returncode
    pr = open_pr(gh, name, owner)
    if rc == 0:
        return "conforms", (f"open PR #{pr['number']} is no longer needed" if pr else "")
    if rc == 2:
        return "skipped:generator-exit-2", "nothing inspected"
    if rc != 1:
        return f"skipped:generator-exit-{rc}", "the generator could not render this file safely"

    rc = shell.run(gen + ["--write"], check=False).returncode
    if rc not in (0, 1):
        return f"skipped:write-exit-{rc}", ""
    changed = changed_paths(shell, dest)
    if not changed:
        return "skipped:write-made-no-change", "drift the generator does not fix"

    if pr:
        if all(read_local(dest, p) == read_remote(gh, name, p, BRANCH) for p in changed):
            return "skipped:pr-up-to-date", f"PR #{pr['number']}"
        if pr.get("commits", 1) != 1:
            return "skipped:pr-has-extra-commits", f"PR #{pr['number']} carries commits the reconciler did not make"
        status, lease = ("updated" if opts.apply else "would-update"), pr["head"]["sha"]
    else:
        lease = branch_head(gh, name)
        if lease:
            return "skipped:branch-without-open-pr", f"`{BRANCH}` exists with no open PR; delete it to re-propose"
        status = "opened" if opts.apply else "would-open"

    if not opts.apply:
        return status, ", ".join(changed)

    # The default branch is never a push target: the refspec names the reconciler branch only.
    assert BRANCH != default
    shell.run(["git", "-C", dest, "checkout", "--quiet", "-B", BRANCH])
    shell.run(["git", "-C", dest, "add", "--", *changed])
    shell.run(["git", "-C", dest, "-c", f"user.name={opts.git_name}", "-c", f"user.email={opts.git_email}",
               "commit", "--quiet", "-m", TITLE,
               "-m", f"Rendered by dependabot/reconcile.py from policy version {policy['version']}."])
    shell.run(["git", "-C", dest, *GIT_AUTH, "push", "--quiet",
               f"--force-with-lease=refs/heads/{BRANCH}:{lease or ''}",
               "origin", f"HEAD:refs/heads/{BRANCH}"])
    body = pr_body(policy, default)
    if pr:
        gh.run(["pr", "edit", str(pr["number"]), "--repo", name, "--body-file", "-"], input_text=body)
        return status, f"PR #{pr['number']}"
    out = gh.run(["pr", "create", "--repo", name, "--base", default, "--head", BRANCH,
                  "--title", TITLE, "--body-file", "-"], input_text=body).stdout.strip()
    return status, out


def main(argv=None, gh=None, shell=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--owner", required=True)
    ap.add_argument("--generator", required=True, help="path to a simtabi/agent-kit checkout")
    ap.add_argument("--policy", default=common.DEFAULT_POLICY)
    ap.add_argument("--apply", action="store_true", help="push branches and open/refresh PRs")
    ap.add_argument("--repo", action="append", default=[], help="limit to these names (repeatable)")
    ap.add_argument("--git-name", default=os.environ.get("RECONCILE_GIT_NAME", "Imani Manyara"))
    ap.add_argument("--git-email", default=os.environ.get("RECONCILE_GIT_EMAIL", "imanimanyara@users.noreply.github.com"))
    opts = ap.parse_args(argv)
    opts.policy = os.path.abspath(opts.policy)
    opts.generator_script = os.path.join(os.path.abspath(opts.generator), GENERATOR)
    gh, shell = gh or common.Gh(), shell or Shell()

    policy = common.load_policy(opts.policy)
    kind = common.account_kind(policy, opts.owner)
    if not os.path.isfile(opts.generator_script):
        print(f"reconcile: generator not found at {opts.generator_script}", file=sys.stderr)
        return 2

    repos = common.list_repos(gh, opts.owner, kind)
    if opts.repo:
        wanted = {r.split("/")[-1].lower() for r in opts.repo}
        repos = [r for r in repos if r["name"].lower() in wanted]
    active, skipped = common.active_repos(gh, policy, repos)
    rows = [(name, f"skipped:{reason.split(':')[0]}", reason) for name, reason in skipped]
    errors = 0
    workdir = tempfile.mkdtemp(prefix="dependabot-reconcile-")
    try:
        for repo in active:
            try:
                status, note = reconcile_repo(repo, opts.owner, gh, shell, opts, policy, workdir)
            except Exception as exc:  # one repository's failure must not stop the others
                errors += 1
                status, note = "error", str(exc)[:300]
            rows.append((repo["full_name"], status, note))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    rows.sort(key=lambda r: r[0].lower())
    mode = "apply" if opts.apply else "dry run"
    head = f"## Dependabot reconcile: {opts.owner} ({mode})\n\n{len(repos)} repositories listed, {len(active)} active.\n\n"
    text = head + common.markdown_table(["repo", "status", "note"], rows)
    print(text)
    common.write_summary(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
