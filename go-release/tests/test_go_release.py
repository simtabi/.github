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
README = ROOT / "go-release" / "README.md"

# The shared workflow signs every caller's provenance, so a verify command has to name it.
SIGNER = "--signer-workflow simtabi/.github/.github/workflows/go-release.yml"

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

    def input_block(self, name):
        m = re.search(r"\n      " + re.escape(name) + r":\n((?:        .*\n)+)", self.text)
        self.assertIsNotNone(m, f"no {name} input")
        return m.group(1)

    def job(self):
        return re.search(r"^jobs:\n((?:[ \t]+.*\n|\n)+)", self.text, re.M).group(1)

    def test_the_runner_is_an_input_defaulting_to_ubuntu(self):
        block = self.input_block("runs-on")
        self.assertIn("required: false", block)
        self.assertRegex(block, r"default: ['\"]?ubuntu-latest['\"]?\n")
        self.assertRegex(self.job(), r"\n    runs-on: \$\{\{ inputs\.runs-on \}\}\n")

    def test_the_environment_is_an_optional_input(self):
        block = self.input_block("environment")
        self.assertIn("required: false", block)
        self.assertRegex(block, r"default: ''\n")
        self.assertRegex(self.job(), r"\n    environment: \$\{\{ inputs\.environment \}\}\n")

    def test_the_signpath_token_is_an_optional_secret_for_goreleaser(self):
        secrets = re.search(r"\n    secrets:\n((?:      .*\n)+)", self.text)
        self.assertIsNotNone(secrets, "workflow_call declares no secrets")
        m = re.search(r"      SIGNPATH_API_TOKEN:\n((?:        .*\n)+)", secrets.group(1))
        self.assertIsNotNone(m, "no SIGNPATH_API_TOKEN secret")
        self.assertIn("required: false", m.group(1))
        step = re.search(r"- name: Run GoReleaser\n((?:        .*\n)+)", self.text).group(1)
        self.assertIn("SIGNPATH_API_TOKEN: ${{ secrets.SIGNPATH_API_TOKEN }}", step)

    def test_attestations_skip_a_private_repository(self):
        steps = re.findall(r"\n((?:      - name: .*\n)(?:        .*\n)*)", self.text)
        attest = [st for st in steps if "actions/attest-build-provenance" in st]
        self.assertEqual(len(attest), 2, "expected two attestation steps")
        for st in attest:
            self.assertRegex(st, r"\n        if: .*github\.event\.repository\.private == false", st)


    def test_node_defaults_to_the_latest_release(self):
        m = re.search(r"\n      node-version:\n(?:        .*\n)*?        default: (\S+)", self.text)
        self.assertIsNotNone(m, "no node-version input")
        self.assertEqual(m.group(1), "latest")
        self.assertIn("node-version: ${{ inputs.node-version }}", self.text)


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

    def test_it_says_how_to_pin_a_version(self):
        self.assertRegex(self.text, r"# replace with @<commit>  # vX\.Y\.Z when copying")

    def test_it_calls_the_shared_workflow(self):
        self.assertIn("uses: simtabi/.github/.github/workflows/go-release.yml@", self.text)
        for perm in ("contents: write", "id-token: write", "attestations: write"):
            self.assertIn(perm, self.text)


if __name__ == "__main__":
    unittest.main()


class VerifyCommands(unittest.TestCase):
    """Every `gh attestation verify` shown names this workflow as the signer: without it, gh expects
    a workflow in the caller's repository and the check fails (simtabi/authama v0.1.6, 2026-11-13)."""

    def test_each_verify_command_names_the_shared_signer(self):
        found = 0
        for path in (WORKFLOW, TEMPLATE, README):
            text = re.sub(r"\\\n\s*", " ", path.read_text())
            for line in text.splitlines():
                if "gh attestation verify" not in line:
                    continue
                found += 1
                self.assertIn(SIGNER, " ".join(line.split()), f"{path.name}: {line.strip()}")
        self.assertGreaterEqual(found, 3, "the workflow, template and README should each show the command")
