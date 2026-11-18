"""Tests for release-train/train.py. The fake GitHub answers only the calls train.py makes, and
refuses anything else, so a new call fails here instead of passing against a fake that can do more
than GitHub."""
import datetime as dt
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import train  # noqa: E402

ET = train.TZ
REPO = "laranail/package-tools"
CHANGELOG = """# Changelog

## [Unreleased]

### Fixed

- A fix.

## [0.1.15] - 2026-11-18

- Earlier.

[Unreleased]: https://github.com/laranail/package-tools/compare/v0.1.15...HEAD
[0.1.15]: https://github.com/laranail/package-tools/compare/v0.1.14...v0.1.15
"""


def at(y, m, d, hh=12, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


def pr(number, version, merged=True, merge_sha="m" * 40, state="closed", labels=()):
    return {
        "number": number, "state": state, "merged_at": "2026-11-21T15:00:00Z" if merged else None,
        "merge_commit_sha": merge_sha, "html_url": f"https://github.com/{REPO}/pull/{number}",
        "head": {"ref": f"release/train-{version}"},
        "base": {"ref": "main", "repo": {"default_branch": "main"}},
        "labels": [{"name": n} for n in labels],
    }


class FakeGh:
    def __init__(self, tags=None, prs=None, changelog=CHANGELOG, head="h" * 40, between=(),
                 commit_prs=None, approvers=(), published=()):
        self._tags, self._prs, self._changelog, self._head = dict(tags or {}), list(prs or []), changelog, head
        self._between, self._commit_prs = list(between), dict(commit_prs or {})
        self._approvers, self._published = set(approvers), set(published)
        self.writes = []

    def tags(self, repo):
        return dict(self._tags)

    def release_prs(self, repo):
        return list(self._prs)

    def file(self, repo, path, ref):
        assert path == "CHANGELOG.md" and ref == "main"
        return self._changelog, "blob-sha"

    def api(self, path, paginate=False):
        if path == f"repos/{REPO}":
            return {"default_branch": "main"}
        raise AssertionError(f"unexpected api call {path}")

    def head(self, repo, branch):
        return self._head

    def commits_between(self, repo, base, head):
        return [{"sha": s} for s in self._between]

    def commit_prs(self, repo, sha):
        return self._commit_prs.get(sha, [])

    def labelled_by(self, repo, number, label):
        assert label == train.APPROVED_LABEL
        return set(self._approvers)

    def release_published(self, repo, tag):
        return tag in self._published

    def create_tag(self, repo, tag, sha):
        self.writes.append(("tag", tag, sha))
        self._tags[tag] = sha

    def send(self, method, path, body):
        self.writes.append((method, path, body))
        if path.endswith("/pulls"):
            return {"html_url": f"https://github.com/{REPO}/pull/99"}
        return {}


class Versions(unittest.TestCase):
    def test_parse_and_order(self):
        self.assertEqual(train.parse_tag("v1.4.2-rc.10"), ((1, 4, 2), "rc", 10))
        self.assertIsNone(train.parse_tag("v1.4.2-rc10"))
        self.assertIsNone(train.parse_tag("1.4.2"))
        self.assertEqual(train.latest_final(["v0.1.9", "v0.1.10", "v0.2.0-rc.1", "src/v9.0.0"]), (0, 1, 10))
        self.assertEqual(train.rc_numbers(["v1.0.0-rc.2", "v1.0.0-rc.10", "v1.0.0-beta.1"], (1, 0, 0)), [2, 10])

    def test_bump(self):
        fixed, added = "\n### Fixed\n\n- x\n", "\n### Added\n\n- x\n"
        removed, empty = "\n### Removed\n\n- x\n", "\n### Fixed\n\n"
        self.assertEqual(train.bump((0, 1, 15), fixed), (0, 1, 16))
        self.assertEqual(train.bump((0, 1, 15), added), (0, 1, 16))
        self.assertEqual(train.bump((0, 1, 15), removed), (0, 2, 0))
        self.assertEqual(train.bump((1, 4, 2), fixed), (1, 4, 3))
        self.assertEqual(train.bump((1, 4, 2), added), (1, 5, 0))
        self.assertEqual(train.bump((1, 4, 2), removed), (2, 0, 0))
        self.assertEqual(train.bump((1, 4, 2), "\n### Changed\n\n- BREAKING: x\n"), (2, 0, 0))
        self.assertIsNone(train.bump((1, 4, 2), empty))
        self.assertIsNone(train.bump((1, 4, 2), None))
        self.assertEqual(train.bump(None, fixed), (0, 1, 0))

    def test_cut_changelog(self):
        out = train.cut_changelog(CHANGELOG, (0, 1, 16), dt.date(2026, 11, 24), (0, 1, 15))
        self.assertIn("## [Unreleased]\n\n## [0.1.16] - 2026-11-24\n\n### Fixed\n\n- A fix.", out)
        self.assertEqual(train.unreleased(out).strip(), "")
        self.assertIn("[Unreleased]: https://github.com/laranail/package-tools/compare/v0.1.16...HEAD\n"
                      "[0.1.16]: https://github.com/laranail/package-tools/compare/v0.1.15...v0.1.16\n", out)

    def test_train_date(self):
        self.assertEqual(train.train_date(at(2026, 11, 20, 18, 7)), dt.date(2026, 11, 24))  # Friday cut
        self.assertEqual(train.train_date(at(2026, 11, 24, 10, 17)), dt.date(2026, 11, 24))  # Tuesday


class Cut(unittest.TestCase):
    now = at(2026, 11, 20, 18, 7)

    def test_dry_run_writes_nothing(self):
        gh = FakeGh(tags={"v0.1.15": "a" * 40})
        self.assertEqual(train.cut(gh, REPO, self.now, False), ("would-open", "Release 0.1.16 for 2026-11-24"))
        self.assertEqual(gh.writes, [])

    def test_apply_opens_the_release_pull_request(self):
        gh = FakeGh(tags={"v0.1.15": "a" * 40})
        status, url = train.cut(gh, REPO, self.now, True)
        self.assertEqual(status, "opened")
        methods = [(w[0], w[1]) for w in gh.writes]
        self.assertEqual(methods, [("POST", f"repos/{REPO}/git/refs"), ("PUT", f"repos/{REPO}/contents/CHANGELOG.md"),
                                   ("POST", f"repos/{REPO}/pulls")])
        self.assertEqual(gh.writes[0][2]["ref"], "refs/heads/release/train-0.1.16")
        self.assertEqual(gh.writes[2][2]["title"], "Release 0.1.16")

    def test_skips(self):
        self.assertEqual(train.cut(FakeGh(prs=[pr(5, "0.1.16", merged=False, state="open")]), REPO, self.now, True)[0], "skipped:open")
        self.assertEqual(train.cut(FakeGh(tags={"v0.1.15": "a"}, prs=[pr(5, "0.1.16")]), REPO, self.now, True)[0], "skipped:waiting")
        nothing = CHANGELOG.replace("### Fixed\n\n- A fix.\n", "")
        self.assertEqual(train.cut(FakeGh(changelog=nothing), REPO, self.now, True)[0], "skipped:nothing")


class Tag(unittest.TestCase):
    now = at(2026, 11, 21, 12, 37)

    def test_first_rc_on_the_merge_commit(self):
        gh = FakeGh(tags={"v0.1.15": "a" * 40}, prs=[pr(5, "0.1.16", merge_sha="m" * 40)])
        self.assertEqual(train.tag(gh, REPO, self.now, True)[0], "tagged")
        self.assertEqual(gh.writes, [("tag", "v0.1.16-rc.1", "m" * 40)])

    def test_next_rc_only_for_release_fixes(self):
        tags = {"v0.1.15": "a" * 40, "v0.1.16-rc.1": "m" * 40}
        fix = {"html_url": "u/7", "labels": [{"name": "release-fix"}]}
        gh = FakeGh(tags=tags, prs=[pr(5, "0.1.16")], between=["c1"], commit_prs={"c1": [fix]})
        self.assertEqual(train.tag(gh, REPO, self.now, True)[0], "tagged")
        self.assertEqual(gh.writes, [("tag", "v0.1.16-rc.2", "h" * 40)])

    def test_freeze_breach_tags_nothing(self):
        tags = {"v0.1.15": "a" * 40, "v0.1.16-rc.1": "m" * 40}
        feature = {"html_url": "u/8", "labels": []}
        gh = FakeGh(tags=tags, prs=[pr(5, "0.1.16")], between=["c1"], commit_prs={"c1": [feature]})
        self.assertEqual(train.tag(gh, REPO, self.now, True), ("freeze-breach", "merged without release-fix: u/8"))
        self.assertEqual(gh.writes, [])

    def test_nothing_to_do(self):
        self.assertEqual(train.tag(FakeGh(), REPO, self.now, True)[0], "skipped:none")
        tags = {"v0.1.16-rc.1": "m" * 40}
        self.assertEqual(train.tag(FakeGh(tags=tags, prs=[pr(5, "0.1.16")]), REPO, self.now, True)[0], "up-to-date")


class Promote(unittest.TestCase):
    tuesday = at(2026, 11, 24, 10, 17)
    tags = {"v0.1.15": "a" * 40, "v0.1.16-rc.1": "m" * 40, "v0.1.16-rc.2": "r" * 40}

    def run_promote(self, gh, now=None, skip=()):
        return train.promote(gh, REPO, now or self.tuesday, True, ["imanimanyara"], set(skip))

    def test_tags_the_last_rc_commit(self):
        gh = FakeGh(tags=self.tags, prs=[pr(5, "0.1.16")], approvers={"imanimanyara"}, published={"v0.1.16-rc.2"})
        self.assertEqual(self.run_promote(gh)[0], "tagged")
        self.assertEqual(gh.writes, [("tag", "v0.1.16", "r" * 40)])

    def test_waits_and_skips(self):
        base = dict(tags=self.tags, prs=[pr(5, "0.1.16")], published={"v0.1.16-rc.2"})
        self.assertEqual(self.run_promote(FakeGh(**base))[0], "waiting:approval")
        self.assertEqual(self.run_promote(FakeGh(**base, approvers={"someone-else"}))[0], "waiting:approval")
        self.assertEqual(self.run_promote(FakeGh(tags=self.tags, prs=[pr(5, "0.1.16")], approvers={"imanimanyara"}))[0],
                         "waiting:rc-release")
        self.assertEqual(self.run_promote(FakeGh(**base), now=at(2026, 11, 23))[0], "skipped:not-tuesday")
        self.assertEqual(self.run_promote(FakeGh(**base), skip={"2026-11-24"})[0], "skipped:calendar")

    def test_writes_nothing_unless_tagged(self):
        gh = FakeGh(tags=self.tags, prs=[pr(5, "0.1.16")])
        self.run_promote(gh)
        self.assertEqual(gh.writes, [])


class Config(unittest.TestCase):
    def test_shipped_config_loads(self):
        cfg = train.load_config()
        self.assertGreaterEqual(len(cfg["repos"]), 2)
        self.assertIn("imanimanyara", cfg["owners"])

    def test_refuses_bad_config(self):
        import tempfile
        for bad in ({"version": 1, "owners": [], "repos": []},
                    {"version": 1, "owners": ["x"], "repos": ["adelsaiq/site"]},
                    {"version": 1, "owners": ["x"], "repos": [], "skip": ["2026-11-25"]}):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(bad, fh)
            with self.assertRaises(ValueError):
                train.load_config(fh.name)
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main()
