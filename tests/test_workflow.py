"""Offline behavioral checks. No live domains, credentials or client sessions."""
import copy
import hashlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "domain-network-investigator"
sys.path[:0] = [str(ROOT / "scripts"), str(SKILL / "scripts")]
import collect_public
import compare_evidence
import dictionary_diff
import init_state
import install_skill
import package_skill
import state_tool


def snapshot(sid, names, digest, profile="team-001"):
    return {"profile_id": profile, "snapshot_id": sid,
            "entries": [{"name": n} for n in names],
            "summary": {"source_url": "https://source.example/names.js", "sha256": digest,
                        "retrieved_at": "2026-01-03T10:00:00Z", "registration_utc": "2026-01-02T08:00:00Z"}}


class DictionaryTests(unittest.TestCase):
    def test_history_distinguishes_new_from_reappeared(self):
        old = snapshot("old", ["A", "B"], "a")
        last = snapshot("last", ["B", "C"], "b")
        current = snapshot("now", ["A", "B", "C", "D"], "c")
        result = dictionary_diff.compare(current, [old, last])
        self.assertEqual([x["name"] for x in result["new_to_profile_dictionary_history"]], ["D"])
        self.assertEqual([x["name"] for x in result["reappeared"]], ["A"])
        self.assertNotIn("name_created_at_proxy", result["new_to_profile_dictionary_history"][0])
        dated = dictionary_diff.compare(current, [old, last], registration_date_proxy=True)
        self.assertEqual(dated["new_to_profile_dictionary_history"][0]["name_created_at_proxy"], "2026-01-02T08:00:00Z")

    def test_baseline_does_not_date_names(self):
        result = dictionary_diff.compare(snapshot("first", ["A"], "a"), [], True)
        self.assertTrue(result["is_first_baseline"])
        self.assertNotIn("name_created_at_proxy", result["new_to_profile_dictionary_history"][0])

    def test_copied_dictionary_is_not_new(self):
        old = snapshot("old", ["A"], "same")
        new = snapshot("new", ["A"], "same")
        new["summary"]["source_url"] = "https://younger.example/names.js"
        result = dictionary_diff.compare(new, [old], True)
        self.assertTrue(result["same_source_bytes_as_previous"])
        self.assertEqual(result["counts"]["added_since_previous"], 0)
        self.assertEqual(result["new_to_profile_dictionary_history"], [])

    def test_identical_hash_inconsistent_parse_rejected(self):
        with self.assertRaisesRegex(ValueError, "Identical source bytes"):
            dictionary_diff.compare(snapshot("new", ["A", "B"], "same"), [snapshot("old", ["A"], "same")])

    def test_cross_team_history_rejected(self):
        with self.assertRaisesRegex(ValueError, "same explicit profile_id"):
            dictionary_diff.compare(snapshot("new", ["B"], "b", "team-002"), [snapshot("old", ["A"], "a")])

    def test_meaningful_name_parts_preserved(self):
        self.assertNotEqual(dictionary_diff.key("A"), dictionary_diff.key("A AI"))
        self.assertNotEqual(dictionary_diff.key("Café"), dictionary_diff.key("Cafe"))

    def test_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "snapshot.json"
            content = json.dumps(snapshot("first", ["A"], "a"))
            source.write_text(content, encoding="utf-8")
            result = subprocess.run([sys.executable, str(SKILL / "scripts/dictionary_diff.py"), str(source), "--out", str(source)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), content)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = init_state.initialize(Path(self.tmp.name) / "state", "Example Team")

    def test_initial_state_valid_and_empty(self):
        registry, profiles = state_tool.validate(self.state)
        self.assertEqual(registry["domains"], [])
        self.assertEqual(profiles["team-001"]["patterns"], [])
        with self.assertRaises(FileExistsError):
            init_state.initialize(self.state, "Other Team")

    def test_cross_profile_pattern_rejected(self):
        path = self.state / "profiles/team-001.json"
        profile = state_tool.read(path)
        profile["patterns"] = [{"id": "p1", "profile_id": "team-002"}]
        path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Cross-profile"):
            state_tool.validate(self.state)

    def test_shared_platform_not_ownership(self):
        path = self.state / "profiles/team-001.json"
        profile = state_tool.read(path)
        profile["patterns"] = [{"id": "p1", "profile_id": "team-001", "scope": "shared_platform", "use": "specific_evidence", "source_refs": ["synthetic"]}]
        path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Shared technology"):
            state_tool.validate(self.state)

    def test_old_domain_new_path_without_mutation(self):
        path = self.state / "registry.json"
        registry = state_tool.read(path)
        registry["domains"] = [{"domain": "project.example", "urls": ["https://project.example/"], "seen_in_profiles": ["team-001"]}]
        path.write_text(json.dumps(registry), encoding="utf-8")
        before = path.read_bytes()
        result = state_tool.triage(self.state, [{"url": "https://project.example/new/ad/", "brand": "New Example"}], "team-001")
        row = result["candidates"][0]
        self.assertEqual((row["domain_novelty"], row["url_novelty"], row["brand_novelty"]), ("known", "new", "new"))
        self.assertEqual(row["team_attribution"], "not_assessed_by_this_tool")
        self.assertEqual(path.read_bytes(), before)


class CollectorTests(unittest.TestCase):
    def test_private_address_rejected(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch.object(collect_public.socket, "getaddrinfo", return_value=answer):
            with self.assertRaisesRegex(ValueError, "Non-public"):
                collect_public.public_url("https://private.example/")

    def test_protocols_have_separate_evidence_and_base_is_resolved(self):
        raw = b'<html><base href="/campaign/"><title>Example</title><form action="submit"><input name="nonce" value="visitor"></form><a href="next">Next</a></html>'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "evidence/sites"
            out.mkdir(parents=True)
            with patch.multiple(collect_public, ROOT=root, OUT=out, ARGS=SimpleNamespace(assets=0, marker=[])), patch.object(collect_public, "get", side_effect=lambda url: (raw, {"Content-Type": "text/html"}, url, 200)), patch("builtins.print"):
                first = collect_public.scan("http://project.example/")
                second = collect_public.scan("https://project.example/")
            self.assertNotEqual(first["directory"], second["directory"])
            self.assertNotIn("\\", first["directory"])
            self.assertEqual(second["links"], ["https://project.example/campaign/next"])
            self.assertEqual(second["forms"][0]["resolved_action"], "https://project.example/campaign/submit")
            self.assertNotIn("value", second["forms"][0]["fields"][0])
            self.assertEqual(second["markers"], {})
            self.assertEqual((root / first["directory"] / "page.html").read_bytes(), raw)

    def test_old_windows_paths_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = b"customCode = 'shared';"
            records = []
            for host in ("one.example", "two.example"):
                directory = root / "evidence/sites" / host
                directory.mkdir(parents=True)
                (directory / "asset.js").write_bytes(content)
                records.append({"url": "https://" + host, "domain": host, "status": 200,
                                "directory": "evidence\\sites\\" + host,
                                "assets": [{"url": "https://" + host + "/asset.js", "file": "asset.js", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}]})
            (root / "fingerprints.json").write_text(json.dumps(records), encoding="utf-8")
            result = compare_evidence.compare([root])
            self.assertEqual(len(result["shared_assets"]), 1)
            (root / "evidence/sites/one.example/asset.js").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                compare_evidence.compare([root])


class DistributionTests(unittest.TestCase):
    def test_install_clients_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            for client, folder in (("codex", ".agents"), ("claude", ".claude")):
                target = install_skill.destination(client, project=tmp)
                self.assertIn(folder, target.parts)
                install_skill.install(target)
                self.assertEqual((target / "SKILL.md").read_bytes(), (SKILL / "SKILL.md").read_bytes())
                self.assertFalse(list(target.rglob("__pycache__")))
                with self.assertRaises(FileExistsError):
                    install_skill.install(target)

    def test_zip_portable_complete_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = package_skill.package(Path(tmp) / "one")
            two = package_skill.package(Path(tmp) / "two")
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as zf:
                files = zf.namelist()
                self.assertIn("domain-network-investigator/SKILL.md", files)
                self.assertIn("domain-network-investigator/references/agent-guide.md", files)
                self.assertIn("domain-network-investigator/LICENSE", files)
                self.assertFalse(any("\\" in name or "__pycache__" in name or "investigation-state" in name for name in files))
                self.assertTrue(all(name.startswith("domain-network-investigator/") for name in files))

    def test_frontmatter_and_relative_markdown_links(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        header = skill.split("---", 2)[1]
        self.assertIn("name: domain-network-investigator", header)
        description = re.search(r"^description: (.+)$", header, re.M).group(1)
        self.assertLessEqual(len(description), 200)
        self.assertEqual((ROOT / "LICENSE").read_bytes(), (SKILL / "LICENSE").read_bytes())
        for path in ROOT.rglob("*.md"):
            if ".git" in path.parts:
                continue
            for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                self.assertTrue((path.parent / target.split("#")[0]).exists(), str(path) + " -> " + target)


if __name__ == "__main__":
    unittest.main()
