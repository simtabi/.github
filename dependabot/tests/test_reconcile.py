import base64
import copy
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402
import reconcile  # noqa: E402

POLICY = common.load_policy()
RENDERED = "# managed\nversion: 2\nupdates: []\n"


def repo(name, **kw):
    r = {"full_name": f"simtabi/{name}", "name": name, "default_branch": "main", "archived": False,
         "fork": False, "size": 10}
    r.update(kw)
    return r


class FakeGh:
    def __init__(self, routes):
        self.routes, self.runs = routes, []

    def api(self, path, paginate=False):
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise common.GhError(f"404 {path}")

    def run(self, args, input_text=None, check=True):
        self.runs.append(args)
        return subprocess.CompletedProcess(args, 0, "https://github.com/simtabi/x/pull/1\n", "")


class FakeShell:
    """git clone makes a directory; the generator answers per repo; --write writes the file."""

    def __init__(self, generator_rc):
        self.generator_rc, self.cmds = generator_rc, []

    def run(self, cmd, check=True, input_text=None):
        self.cmds.append(cmd)
        if "clone" in cmd:
            os.makedirs(cmd[-1])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "check" in cmd and "--strict" in cmd:
            dest = cmd[cmd.index("check") + 1]
            name = os.path.basename(dest).split("__", 1)[1]
            if "--write" in cmd:
                os.makedirs(os.path.join(dest, ".github"), exist_ok=True)
                with open(os.path.join(dest, ".github", "dependabot.yml"), "w") as fh:
                    fh.write(RENDERED)
            return subprocess.CompletedProcess(cmd, self.generator_rc[name], "", "")
        if "status" in cmd:
            dest = cmd[2]
            dirty = os.path.exists(os.path.join(dest, ".github", "dependabot.yml"))
            return subprocess.CompletedProcess(cmd, 0, "?? .github/dependabot.yml\0" if dirty else "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


class FilterTest(unittest.TestCase):
    def test_active_filter(self):
        pol = copy.deepcopy(POLICY)
        pol["exclude"] = [{"repo": "simtabi/legacy", "reason": "frozen"}]
        repos = [repo("ok"), repo("old", archived=True), repo("fork", fork=True), repo("legacy"),
                 repo("empty", size=0), repo("tiny", size=0)]
        gh = FakeGh({"repos/simtabi/empty/branches": [], "repos/simtabi/tiny/branches": [{"name": "main"}]})
        active, skipped = common.active_repos(gh, pol, repos)
        self.assertEqual([r["name"] for r in active], ["ok", "tiny"])
        self.assertEqual(dict(skipped), {"simtabi/old": "archived", "simtabi/fork": "fork",
                                         "simtabi/legacy": "excluded: frozen", "simtabi/empty": "empty"})

    def test_client_accounts_never_managed(self):
        for owner in ("adelsaiq", "dannielagumo", "joemanch"):
            with self.subTest(owner), self.assertRaises(ValueError):
                common.account_kind(POLICY, owner)
        self.assertEqual(common.account_kind(POLICY, "laranail"), "org")
        self.assertEqual(common.account_kind(POLICY, "imanimanyara"), "user")

    def test_policy_rejects_client_account(self):
        pol = copy.deepcopy(POLICY)
        pol["accounts"]["orgs"].append("adelsaiq")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            import json
            json.dump(pol, fh)
        try:
            with self.assertRaises(ValueError):
                common.load_policy(fh.name)
        finally:
            os.unlink(fh.name)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.gen = tempfile.mkdtemp()
        script = os.path.join(self.gen, reconcile.GENERATOR)
        os.makedirs(os.path.dirname(script))
        open(script, "w").close()

    def run_main(self, routes, rc, *extra):
        gh, shell = FakeGh(routes), FakeShell(rc)
        out = reconcile.main(["--owner", "simtabi", "--generator", self.gen, *extra], gh=gh, shell=shell)
        return out, gh, shell

    def base_routes(self):
        return {
            "orgs/simtabi/repos": [repo("conforming"), repo("drifting"), repo("broken"), repo("pr-current"),
                                   repo("pr-stale"), repo("closed-pr"), repo("archived", archived=True)],
            "repos/simtabi/pr-current/pulls?": [{"number": 4}],
            "repos/simtabi/pr-current/pulls/4": {"number": 4, "commits": 1, "head": {"sha": "p4"}},
            "repos/simtabi/pr-current/contents/.github/dependabot.yml":
                {"content": base64.b64encode(RENDERED.encode()).decode()},
            "repos/simtabi/pr-stale/pulls?": [{"number": 5}],
            "repos/simtabi/pr-stale/pulls/5": {"number": 5, "commits": 1, "head": {"sha": "p5"}},
            "repos/simtabi/pr-stale/contents/.github/dependabot.yml":
                {"content": base64.b64encode(b"old\n").decode()},
            "repos/simtabi/closed-pr/git/ref/heads/": {"object": {"sha": "c1"}},
            "repos/": [],  # any other pulls listing: no open PR
        }

    RC = {"conforming": 0, "drifting": 1, "broken": 2, "pr-current": 1, "pr-stale": 1, "closed-pr": 1}

    def test_dry_run_plan(self):
        captured = []
        orig = common.write_summary
        common.write_summary = captured.append
        try:
            code, gh, shell = self.run_main(self.base_routes(), self.RC)
        finally:
            common.write_summary = orig
        self.assertEqual(code, 0)
        table = captured[0]
        for name, status in [("conforming", "conforms"), ("drifting", "would-open"),
                             ("broken", "skipped:generator-exit-2"), ("pr-current", "skipped:pr-up-to-date"),
                             ("pr-stale", "would-update"), ("closed-pr", "skipped:branch-without-open-pr"),
                             ("archived", "skipped:archived")]:
            with self.subTest(name):
                self.assertRegex(table, rf"\| simtabi/{name} \| {status} \|")
        self.assertEqual(gh.runs, [], "a dry run makes no gh writes")
        self.assertFalse([c for c in shell.cmds if "push" in c], "a dry run never pushes")

    def test_apply_pushes_only_the_reconciler_branch(self):
        code, gh, shell = self.run_main(self.base_routes(), self.RC, "--apply")
        self.assertEqual(code, 0)
        pushes = [c for c in shell.cmds if "push" in c]
        self.assertEqual(len(pushes), 2)  # drifting (new) and pr-stale (refresh)
        for push in pushes:
            self.assertEqual(push[-1], "HEAD:refs/heads/chore/dependabot-standard")
            self.assertFalse(any(arg.endswith(":refs/heads/main") or arg == "main" for arg in push))
        leases = sorted(next(a for a in p if a.startswith("--force-with-lease")) for p in pushes)
        self.assertEqual(leases, ["--force-with-lease=refs/heads/chore/dependabot-standard:",
                                  "--force-with-lease=refs/heads/chore/dependabot-standard:p5"])
        verbs = sorted(r[1] for r in gh.runs)
        self.assertEqual(verbs, ["create", "edit"])
        create = next(r for r in gh.runs if r[1] == "create")
        self.assertIn("Adopt the Dependabot standard", create)

    def test_error_in_one_repo_is_reported_and_exits_nonzero(self):
        routes = self.base_routes()
        routes = {"repos/simtabi/drifting/pulls?": common.GhError("boom"), **routes}
        captured = []
        orig = common.write_summary
        common.write_summary = captured.append
        try:
            code, _, _ = self.run_main(routes, self.RC)
        finally:
            common.write_summary = orig
        self.assertEqual(code, 1)
        self.assertRegex(captured[0], r"\| simtabi/drifting \| error \| .*boom")
        self.assertRegex(captured[0], r"\| simtabi/conforming \| conforms \|")

    def test_pr_with_extra_commits_is_left_alone(self):
        routes = self.base_routes()
        routes["repos/simtabi/pr-stale/pulls/5"] = {"number": 5, "commits": 2, "head": {"sha": "p5"}}
        code, gh, shell = self.run_main(routes, self.RC, "--apply", "--repo", "pr-stale")
        self.assertEqual(code, 0)
        self.assertFalse([c for c in shell.cmds if "push" in c])


if __name__ == "__main__":
    unittest.main()
