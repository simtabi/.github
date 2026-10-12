import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402
import merge  # noqa: E402

POLICY = common.load_policy()


def policy(**merge_overrides):
    p = copy.deepcopy(POLICY)
    p["merge"].update(merge_overrides)
    return p


def pr(**kw):
    base = {
        "repo": "laranail/emojis", "number": 7, "draft": False, "mergeable_state": "clean", "labels": [],
        "head_sha": "abc", "head_ref": "dependabot/github_actions/shivammathur/setup-php-2.37.2",
        "title": "chore(actions): bump shivammathur/setup-php from 2.37.1 to 2.37.2",
    }
    base.update(kw)
    return base


def green(*names):
    return [{"name": n, "status": "completed", "conclusion": "success"} for n in names]


GREEN3 = green("tests (8.4)", "tests (8.5)", "static analysis")
COMPOSER_PATCH = dict(head_ref="dependabot/composer/laravel/framework-13.1.2",
                      title="deps(composer): bump laravel/framework from 13.1.1 to 13.1.2")
COMPOSER_MINOR = dict(head_ref="dependabot/composer/laravel/framework-13.2.0",
                      title="deps(composer): bump laravel/framework from 13.1.1 to 13.2.0")


class DecideTest(unittest.TestCase):
    # (label, pr kwargs, checks, statuses, floor, policy, expected merge, reason fragment)
    CASES = [
        ("actions patch, all green", {}, GREEN3, [], 3, POLICY, True, "github-actions patch"),
        ("failing check", {}, GREEN3[:2] + [{"name": "static analysis", "status": "completed", "conclusion": "failure"}],
         [], 3, POLICY, False, "failing: static analysis=failure"),
        ("pending check", {}, GREEN3[:2] + [{"name": "static analysis", "status": "in_progress", "conclusion": None}],
         [], 3, POLICY, False, "pending: static analysis"),
        ("pending commit status", {}, GREEN3, [{"context": "GitGuardian", "state": "pending"}], 3, POLICY,
         False, "pending: GitGuardian"),
        ("failed commit status", {}, GREEN3, [{"context": "GitGuardian", "state": "failure"}], 3, POLICY,
         False, "failing: GitGuardian=failure"),
        ("neutral and skipped are fine", {}, green("tests", "lint") + [
            {"name": "docs", "status": "completed", "conclusion": "skipped"},
            {"name": "scorecard", "status": "completed", "conclusion": "neutral"}], [], 4, POLICY, True, "4 checks"),
        ("below floor", {}, GREEN3, [], 5, POLICY, False, "3 check runs reported, floor is 5"),
        ("no floor, test-like check present", {}, green("tests (8.4)"), [], None, POLICY, True, "floor 1"),
        ("no floor, no test-like check", {}, green("lint"), [], None, POLICY, False, "no test-like check"),
        ("no floor, no checks at all", {}, [], [], None, POLICY, False, "0 check runs reported, floor is 1"),
        ("hold label", {"labels": ["dependencies", "automerge:hold"]}, GREEN3, [], 3, POLICY, False, "held by label"),
        ("draft", {"draft": True}, GREEN3, [], 3, POLICY, False, "draft"),
        ("not clean", {"mergeable_state": "blocked"}, GREEN3, [], 3, POLICY, False, "'blocked'"),
        ("unknown mergeable state", {"mergeable_state": "unknown"}, GREEN3, [], 3, POLICY, False, "'unknown'"),
        ("actions major", {"title": "chore(actions): bump actions/checkout from 6 to 7",
                           "head_ref": "dependabot/github_actions/actions/checkout-7"},
         GREEN3, [], 3, policy(default="minor"), False, "major update"),
        ("composer 0.x minor is major", {"head_ref": "dependabot/composer/laranail/console-0.2.0",
                                         "title": "deps(composer): bump laranail/console from 0.1.4 to 0.2.0"},
         GREEN3, [], 3, policy(default="minor"), False, "major update"),
        ("actions group counts as minor", {"head_ref": "dependabot/github_actions/github-actions-minor-and-patch-1a2b",
                                           "title": "chore(actions): bump the github-actions-minor-and-patch group with 3 updates"},
         GREEN3, [], 3, POLICY, True, "group github-actions-minor-and-patch"),
        ("composer group under actions-only", {"head_ref": "dependabot/composer/composer-minor-and-patch-1a2b",
                                               "title": "deps(composer): bump the composer-minor-and-patch group with 2 updates"},
         GREEN3, [], 3, POLICY, False, "composer minor not allowed by merge policy 'actions'"),
        ("composer group under minor", {"head_ref": "dependabot/composer/composer-minor-and-patch-1a2b",
                                        "title": "deps(composer): bump the composer-minor-and-patch group across 1 directory with 2 updates"},
         GREEN3, [], 3, policy(default="minor"), True, "composer minor"),
        ("foreign group name is not trusted", {"head_ref": "dependabot/composer/minor-and-patch-1a2b",
                                               "title": "Bump the minor-and-patch group with 2 updates"},
         GREEN3, [], 3, policy(default="minor"), False, "not the policy group"),
        ("actions-only rejects composer patch", COMPOSER_PATCH, GREEN3, [], 3, POLICY, False,
         "composer patch not allowed by merge policy 'actions'"),
        ("repo override to patch accepts composer patch", COMPOSER_PATCH, GREEN3, [], 3,
         policy(overrides={"laranail/emojis": "patch"}), True, "composer patch"),
        ("patch override still rejects composer minor", COMPOSER_MINOR, GREEN3, [], 3,
         policy(overrides={"laranail/emojis": "patch"}), False, "composer minor not allowed"),
        ("org wildcard override", COMPOSER_MINOR, GREEN3, [], 3, policy(overrides={"laranail/*": "minor"}), True,
         "composer minor"),
        ("repo override beats org wildcard", COMPOSER_PATCH, GREEN3, [], 3,
         policy(overrides={"laranail/*": "minor", "laranail/emojis": "off"}), False, "policy 'off'"),
        ("off rejects actions", {}, GREEN3, [], 3, policy(default="off"), False, "policy 'off'"),
        ("unparseable title", {"title": "Bump something"}, GREEN3, [], 3, POLICY, False, "not recognised"),
        ("sha pins are unparseable", {"title": "bump foo/bar from 1a2b3c4 to 5d6e7f8"}, GREEN3, [], 3, POLICY,
         False, "not recognised"),
        ("pre-release is unparseable", {"title": "bump foo/bar from 2.0.0 to 2.0.1-rc1"}, GREEN3, [], 3, POLICY,
         False, "not recognised"),
        ("non-dependabot branch", {"head_ref": "feature/x"}, GREEN3, [], 3, POLICY, False, "unknown ecosystem"),
    ]

    def test_cases(self):
        for label, kw, checks, statuses, floor, pol, want, fragment in self.CASES:
            with self.subTest(label):
                ok, reason = merge.decide(pr(**kw), checks, statuses, floor, pol)
                self.assertEqual(ok, want, reason)
                self.assertIn(fragment, reason)

    def test_case_table_is_not_vacuous(self):
        self.assertGreaterEqual(len(self.CASES), 25)
        self.assertTrue(any(c[6] for c in self.CASES) and not all(c[6] for c in self.CASES))


class SemverTest(unittest.TestCase):
    def test_classification(self):
        table = [("1.2.3", "1.2.4", "patch"), ("1.2.3", "1.3.0", "minor"), ("1.2.3", "2.0.0", "major"),
                 ("v4", "v5", "major"), ("6", "6.1", "minor"), ("0.1.0", "0.1.1", "patch"),
                 ("0.1.0", "0.2.0", "major"), ("1.2.3", "1.2.3", None), ("1.3.0", "1.2.9", None),
                 ("1.2.3", "1.2.4-beta", None), ("abc", "def", None), ("1.2.3.4", "1.2.3.5", "patch")]
        for old, new, want in table:
            with self.subTest(f"{old}->{new}"):
                self.assertEqual(merge.semver_change(old, new), want)


class FakeGh:
    def __init__(self, routes):
        self.routes, self.calls, self.runs = routes, [], []

    def api(self, path, paginate=False):
        self.calls.append(path)
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return value
        raise common.GhError(f"no route for {path}")

    def run(self, args, input_text=None, check=True):
        self.runs.append(args)


class MainTest(unittest.TestCase):
    def routes(self):
        return {
            "search/issues": [{"items": [{"repository_url": "https://api.github.com/repos/laranail/emojis", "number": 7}]}],
            "repos/laranail/emojis/pulls/7": {"title": pr()["title"], "head": {"ref": pr()["head_ref"], "sha": "abc"},
                                               "draft": False, "mergeable_state": "clean", "labels": []},
            "repos/laranail/emojis/pulls?state=closed": [
                {"merged_at": "2026-10-01T00:00:00Z", "user": {"login": "imanimanyara"}, "head": {"sha": "old"}}],
            "repos/laranail/emojis/commits/old/check-runs": [{"check_runs": GREEN3}],
            "repos/laranail/emojis/commits/abc/check-runs": [{"check_runs": GREEN3}],
            "repos/laranail/emojis/commits/abc/status": {"statuses": [{"context": "GitGuardian", "state": "success"}]},
        }

    def test_dry_run_never_merges(self):
        gh = FakeGh(self.routes())
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 0)
        self.assertEqual(gh.runs, [])

    def test_apply_merges_pinned_to_head(self):
        gh = FakeGh(self.routes())
        self.assertEqual(merge.main(["--owner", "laranail", "--apply"], gh=gh), 0)
        self.assertEqual(gh.runs, [["pr", "merge", "7", "--repo", "laranail/emojis", "--squash",
                                    "--match-head-commit", "abc"]])

    def test_client_account_refused(self):
        with self.assertRaises(ValueError):
            merge.main(["--owner", "adelsaiq"], gh=FakeGh({}))


if __name__ == "__main__":
    unittest.main()
