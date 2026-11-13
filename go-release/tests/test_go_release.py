"""Guards for the shared Go release: the reusable workflow and the caller template.

The standard (~/.claude/rules/go.md, "Go releases") says Go binaries ship on the GitHub release only,
built on a version tag or on request. These tests read the two files as text, with the standard
library only, the way the rest of this repository's tests do.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "go-release.yml"
TEMPLATE = ROOT / "templates" / "go" / "release.yml"

# Every GoReleaser block that publishes somewhere other than the GitHub release.
CHANNELS = {
    "brews", "homebrew_casks", "scoops", "winget", "chocolateys", "aurs", "aur_sources",
    "snapcrafts", "flatpaks", "nix", "dockers", "dockers_v2", "docker_manifests", "docker_signs",
    "kos", "krews", "npms", "cloudsmiths", "furies", "publishers", "blobs", "uploads", "artifactories",
}


def triggers(text):
    """The top-level keys under `on:`, in order."""
    block = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+)", text, re.M)
    if not block:
        return []
    return re.findall(r"^  ([a-z_]+):", block.group(1), re.M)


class SharedWorkflow(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_it_is_only_ever_called(self):
        self.assertEqual(triggers(self.text), ["workflow_call"])

    def test_the_tag_is_a_required_input(self):
        self.assertRegex(self.text, r"\n      tag:\n(?:        .*\n)*?        required: true")

    def test_it_refuses_every_other_channel(self):
        m = re.search(r"banned='([^']+)'", self.text)
        self.assertIsNotNone(m, "the channel check is gone")
        self.assertEqual(set(m.group(1).split("|")), CHANNELS)

    def test_it_checks_out_the_tag_and_attests(self):
        self.assertIn("ref: refs/tags/${{ inputs.tag }}", self.text)
        self.assertIn("actions/attest-build-provenance", self.text)
        self.assertIn("GORELEASER_CURRENT_TAG: ${{ inputs.tag }}", self.text)


class CallerTemplate(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text()

    def test_it_runs_on_a_version_tag_or_on_request(self):
        self.assertEqual(triggers(self.text), ["push", "workflow_dispatch"])
        push = re.search(r"^  push:\n((?:    .*\n)+)", self.text, re.M).group(1)
        self.assertNotIn("branches", push)
        tags = re.findall(r"^      - '([^']+)'", push, re.M)
        self.assertTrue(tags, "no tag filter")
        for t in tags:
            self.assertRegex(t, r"^v\[0-9\]\+\.", f"tag filter {t!r} is not a version")

    def test_a_dispatch_names_the_tag(self):
        self.assertRegex(self.text, r"workflow_dispatch:\n    inputs:\n      tag:")

    def test_it_calls_the_shared_workflow(self):
        self.assertIn("uses: simtabi/.github/.github/workflows/go-release.yml@", self.text)
        for perm in ("contents: write", "id-token: write", "attestations: write"):
            self.assertIn(perm, self.text)


if __name__ == "__main__":
    unittest.main()
