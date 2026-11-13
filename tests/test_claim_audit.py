#!/usr/bin/env python3
"""Tests for skill-claim-audit. Stdlib only; no network."""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin", "skill-claim-audit")
loader = importlib.machinery.SourceFileLoader("sca", BIN)
spec = importlib.util.spec_from_loader("sca", loader)
sca = importlib.util.module_from_spec(spec)
loader.exec_module(sca)


def make_skill(root, body, files=None):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: demo\ndescription: demo skill\n---\n" + body)
    for rel, content in (files or {}).items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


def run_cli(root, *extra):
    proc = subprocess.run([sys.executable, BIN, root, *extra], capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


class UnitTests(unittest.TestCase):
    def test_frontmatter_name(self):
        meta, _ = sca.split_frontmatter("---\nname: demo\ndescription: d\n---\nbody")
        self.assertEqual(meta["name"], "demo")

    def test_package_normalization(self):
        self.assertEqual(sca.normalize_pkg("Foo_Bar"), "foo-bar")

    def test_requirements_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "requirements.txt"), "w") as fh:
                fh.write("openpyxl>=3.1\n# comment\npandas\n")
            names, files = sca.manifest_packages(tmp)
            self.assertIn("openpyxl", names)
            self.assertIn("requirementstxt", files[0].replace(".", "").replace("/", ""))

    def test_package_json_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "package.json"), "w") as fh:
                json.dump({"dependencies": {"left-pad": "1.0.0"}}, fh)
            names, _ = sca.manifest_packages(tmp)
            self.assertIn("left-pad", names)

    def test_preinstalled_without_manifest_is_high(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "Run `numpy`; it is preinstalled.\n")
            report, code = sca.scan(tmp)
            self.assertEqual(code, 1)
            self.assertEqual(report["findings"][0]["rule"], "CLAIM001")
            self.assertEqual(report["findings"][0]["severity"], "high")

    def test_preinstalled_declared_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "`numpy` is preinstalled.\n")
            with open(os.path.join(tmp, "requirements.txt"), "w") as fh:
                fh.write("numpy\n")
            report, code = sca.scan(tmp)
            self.assertEqual(code, 0)
            self.assertEqual(report["findings"], [])

    def test_repeated_claim_deduped(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "`numpy` is preinstalled.\n`numpy` is preinstalled again.\n")
            report, _ = sca.scan(tmp)
            self.assertEqual(len([f for f in report["findings"] if f["subject"] == "numpy"]), 1)

    def test_auto_configured_without_locator_is_medium(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(
                os.path.join(tmp, "s"),
                "`soffice` is auto-configured via `scripts/office/soffice.py`.\n",
                {"scripts/office/soffice.py": 'import subprocess\nsubprocess.run(["soffice"])\n'},
            )
            report, _ = sca.scan(tmp, "medium")
            rules = {f["rule"] for f in report["findings"]}
            self.assertIn("CLAIM002", rules)

    def test_auto_configured_with_locator_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(
                os.path.join(tmp, "s"),
                "`soffice` is auto-configured via `scripts/find.py`.\n",
                {"scripts/find.py": 'import shutil\nshutil.which("soffice")\n'},
            )
            report, _ = sca.scan(tmp, "medium")
            self.assertNotIn("CLAIM002", {f["rule"] for f in report["findings"]})

    def test_missing_path_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "See `references/missing.md`.\n")
            report, _ = sca.scan(tmp, "medium")
            self.assertIn("CLAIM003", {f["rule"] for f in report["findings"]})

    def test_existing_path_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "See `references/present.md`.\n",
                       {"references/present.md": "ok\n"})
            report, _ = sca.scan(tmp, "medium")
            self.assertNotIn("CLAIM003", {f["rule"] for f in report["findings"]})


class BehaviorTests(unittest.TestCase):
    def test_cli_json_parses_and_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "`numpy` is preinstalled.\n")
            code, out, _ = run_cli(tmp, "--json")
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["skills_scanned"], 1)
            self.assertEqual(data["summary"]["high"], 1)

    def test_cli_clean_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "Just docs, no claims.\n")
            code, out, _ = run_cli(tmp, "--json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["findings"], [])

    def test_cli_missing_root_exit_2(self):
        code, _, err = run_cli("/tmp/definitely-not-a-skill-root-xyz", "--json")
        self.assertEqual(code, 2)
        self.assertIn("error", err)

    def test_fail_on_high_ignores_medium(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_skill(os.path.join(tmp, "s"), "See `references/missing.md`.\n")
            code, out, _ = run_cli(tmp, "--json", "--fail-on", "high")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["summary"]["medium"], 1)


if __name__ == "__main__":
    unittest.main()