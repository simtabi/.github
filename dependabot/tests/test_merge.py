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


class NonVacuityTest(unittest.TestCase):
    """A quiet run must prove it could have read a check, not merely that it read none.

    The gate went 6/10 green on 2026-11-03 while holding no `checks: read`, because those six
    orgs had no open Dependabot pull requests and so never called the API. These cases pin the
    distinction between 'nothing to do' and 'cannot see anything'.
    """

    EMPTY_SEARCH = {"search/issues": [{"items": []}]}

    # The real shapes this control has to tell apart. A generic exception is not a 403, and
    # testing with one is how the first version came to treat an empty repository's 422 as a
    # permission failure.
    DENIED = "gh api --paginate --slurp: gh: Resource not accessible by integration (HTTP 403)"
    NO_COMMIT = "gh api --paginate --slurp: gh: No commit found for SHA: main (HTTP 422)"

    def gh_raising(self, routes, on_check_runs):
        """FakeGh that raises a specific error for check-runs paths."""
        class Raising(FakeGh):
            def api(self, path, paginate=False):
                if "/check-runs" in path:
                    raise common.GhError(on_check_runs)
                return super().api(path, paginate=paginate)
        return Raising(routes)

    def repos_route(self, **extra):
        routes = dict(self.EMPTY_SEARCH)
        routes["orgs/laranail/repos"] = [{"full_name": "laranail/emojis", "default_branch": "main"}]
        routes.update(extra)
        return routes

    def test_quiet_run_passes_when_the_control_verifies(self):
        gh = FakeGh(self.repos_route(**{"repos/laranail/emojis/commits/main/check-runs": [{"check_runs": []}]}))
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 0)

    def test_quiet_run_FAILS_when_checks_are_unreadable(self):
        # The real 403, not a generic exception: that is the only evidence of a missing permission.
        gh = self.gh_raising(self.repos_route(), self.DENIED)
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 1)

    def test_quiet_run_passes_when_there_is_nothing_to_probe(self):
        # An account with no repositories cannot be probed; that is not a permission failure.
        gh = FakeGh(dict(self.EMPTY_SEARCH, **{"orgs/laranail/repos": []}))
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 0)

    def test_an_empty_repository_is_not_read_as_a_permission_failure(self):
        gh = self.gh_raising(self.repos_route(), "gh: Git Repository is empty. (HTTP 409)")
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 0)

    def test_an_empty_repo_answering_422_is_not_a_permission_failure(self):
        """The shape that broke the first version. `simsange`'s newest private repository is
        the empty `simsange/documentation`, whose default_branch is nominally `main`: /commits
        answers 409 but commits/main/check-runs answers 422 'No commit found for SHA'. The
        enumerate-the-benign-shapes version matched 409 and the word 'empty', missed 422, and
        reported a permission failure that would have gone red every quiet week."""
        gh = self.gh_raising(self.repos_route(), self.NO_COMMIT)
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 0)
        ok, detail = merge.checks_readable(gh, "laranail", "org")
        self.assertIsNone(ok, "an inconclusive error must not become a permission verdict")
        self.assertIn("422", detail)

    def test_an_unlistable_account_is_inconclusive_unless_denied(self):
        class NoList(FakeGh):
            def __init__(self, routes, err):
                super().__init__(routes)
                self.err = err

            def api(self, path, paginate=False):
                if "/repos?" in path:
                    raise common.GhError(self.err)
                return super().api(path, paginate=paginate)

        ok, _ = merge.checks_readable(NoList(self.EMPTY_SEARCH, "gh: Not Found (HTTP 404)"), "laranail", "org")
        self.assertIsNone(ok)
        ok, _ = merge.checks_readable(NoList(self.EMPTY_SEARCH, self.DENIED), "laranail", "org")
        self.assertIs(ok, False)

    def test_control_prefers_a_private_repository(self):
        """`checks: read` is enforced on private repos only, so probing a public one can
        report 'readable' while the gate is blind to every repo it actually works on. That is
        what happened on 2026-11-03: simtabi's single pull request passed on the public
        cli-kit-js with the same token that 403'd on four orgs' private repos."""
        routes = dict(self.EMPTY_SEARCH)
        routes["orgs/laranail/repos"] = [
            {"full_name": "laranail/pub", "default_branch": "main", "private": False},
            {"full_name": "laranail/priv", "default_branch": "main", "private": True},
        ]
        # Only the PUBLIC repo is readable; the private one answers a real 403, as in the run.
        routes["repos/laranail/pub/commits/main/check-runs"] = [{"check_runs": []}]

        denied = self.DENIED

        class PrivateDenied(FakeGh):
            def api(self, path, paginate=False):
                if "laranail/priv" in path and "/check-runs" in path:
                    raise common.GhError(denied)
                return super().api(path, paginate=paginate)

        ok, detail = merge.checks_readable(PrivateDenied(routes), "laranail", "org")
        self.assertIs(ok, False, "a public-only read must not pass as verification")
        self.assertIn("laranail/priv", detail)

    def test_control_names_the_visibility_it_verified(self):
        routes = dict(self.EMPTY_SEARCH)
        routes["orgs/laranail/repos"] = [{"full_name": "laranail/priv", "default_branch": "main", "private": True}]
        routes["repos/laranail/priv/commits/main/check-runs"] = [{"check_runs": []}]
        ok, detail = merge.checks_readable(FakeGh(routes), "laranail", "org")
        self.assertIs(ok, True)
        self.assertIn("(private)", detail)

    def test_a_public_only_account_still_verifies(self):
        # No private repository means no private blindness to detect; a public probe is complete.
        routes = dict(self.EMPTY_SEARCH)
        routes["orgs/laranail/repos"] = [{"full_name": "laranail/pub", "default_branch": "main", "private": False}]
        routes["repos/laranail/pub/commits/main/check-runs"] = [{"check_runs": []}]
        ok, detail = merge.checks_readable(FakeGh(routes), "laranail", "org")
        self.assertIs(ok, True)
        self.assertIn("(public)", detail)

    def test_control_reports_absence_not_just_presence(self):
        # The negative half: a control that can only ever say "readable" proves nothing.
        # It must answer False on the real 403, and only on that.
        gh = self.gh_raising(self.repos_route(), self.DENIED)
        ok, detail = merge.checks_readable(gh, "laranail", "org")
        self.assertIs(ok, False)
        self.assertIn("cannot read check runs", detail)

    def test_every_examined_pr_erroring_is_called_out_as_systemic(self):
        gh = FakeGh({"search/issues": [{"items": [
            {"repository_url": "https://api.github.com/repos/laranail/emojis", "number": 7}]}]})
        self.assertEqual(merge.main(["--owner", "laranail"], gh=gh), 1)


if __name__ == "__main__":
    unittest.main()
