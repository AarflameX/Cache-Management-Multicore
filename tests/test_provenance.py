import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.export_run import export_run
from scripts.merge_summaries import merge_summaries
from scripts.run_provenance import GUARD_FIELDS, check_existing, gem5_build_info, preflight
from tests.test_parse_stats import coherence_block


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.data = self.root / "data"
        self.metadata = self.run / "run.json"

    def finish(self, metadata, stats=""):
        (self.run / "DONE").touch()
        self.metadata.write_text(json.dumps(metadata))
        (self.run / "stats.txt").write_text(stats)

    def make_roi(self, cores):
        stats = ""
        for multiplier in (1, 99):
            stats += "---------- Begin Simulation Statistics ----------\n"
            stats += "".join(f"{key} {value}\n" for key, value in
                             coherence_block(multiplier, cores=cores).items())
            stats += "---------- End Simulation Statistics ----------\n"
        self.finish(dict(suite="gap", benchmark="bfs", cores=cores, variant="fixture",
                         roi=1, seed=5489), stats)

    def test_guard_accepts_match_and_reports_every_mismatch(self):
        expected = dict.fromkeys(GUARD_FIELDS, "current")
        self.finish(expected)
        check_existing(self.run, expected)
        for field in GUARD_FIELDS:
            with self.subTest(field=field):
                actual = dict(expected, **{field: "old"})
                self.metadata.write_text(json.dumps(actual))
                with self.assertRaisesRegex(ValueError, field + ".*new --variant"):
                    check_existing(self.run, expected)
                self.assertEqual(json.loads(self.metadata.read_text()), actual)

    def test_guard_refuses_legacy_and_incomplete_runs(self):
        expected = dict.fromkeys(GUARD_FIELDS, "current")
        check_existing(self.root / "missing", expected)
        with self.assertRaisesRegex(ValueError, "not a finished run.*new --variant"):
            check_existing(self.run, expected)
        self.finish({"args": "current"})
        with self.assertRaisesRegex(ValueError, "seed.*new --variant"):
            check_existing(self.run, expected)
        self.assertTrue((self.run / "DONE").exists())

    def test_export_dry_run_and_deterministic_coherence_payload(self):
        self.make_roi(2)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            target = export_run(self.run, self.data, dry_run=True)
            self.assertFalse(self.data.exists())
            self.assertEqual(target, self.data / "fixture/gap_bfs_c2.json")
            export_run(self.run, self.data)
        payload = target.read_text()
        self.assertEqual(output.getvalue().splitlines()[0], f"Would write {target}")
        parsed = json.loads(payload)
        self.assertEqual(parsed["stats"]["L1_invalidations"], 5)
        self.assertEqual(parsed["stats"]["L1_invalidations_per_kinst"], 5 / 3)
        self.assertEqual(parsed["run"], json.loads(self.metadata.read_text()))
        self.assertEqual(payload, json.dumps(parsed, sort_keys=True, indent=2) + "\n")
        (self.run / "FAILED").touch()
        with self.assertRaisesRegex(ValueError, "DONE and no FAILED"):
            export_run(self.run, self.data)

    def test_merge_numeric_core_order_and_coherence_columns(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for cores in (4, 2):
                self.make_roi(cores)
                target = export_run(self.run, self.data)
        exported = json.loads(target.read_text())
        for section in ("run", "stats"):
            exported[section]["cores"] = 10
        (target.parent / "gap_bfs_c10.json").write_text(json.dumps(exported))
        target = merge_summaries(self.data / "fixture")
        with target.open(newline="") as summary:
            rows = list(csv.DictReader(summary))
        self.assertEqual([row["cores"] for row in rows], ["2", "4", "10"])
        self.assertEqual(rows[0]["L1_outgoing_msgs"], "210")
        original = target.read_bytes()
        self.assertEqual(merge_summaries(target.parent).read_bytes(), original)


    def retry_fixture(self):
        base = self.root / "fixture"
        base.mkdir()
        state = self.root / "state"
        state.mkdir()
        binary_dir = self.root / "benchmarks/gap/bin-roi"
        binary_dir.mkdir(parents=True)
        gem5, conf = self.root / "gem5.opt", self.root / "conf"
        for path in (gem5, conf, self.root / "mesi_two_level_se_multi.py",
                     binary_dir / "bfs", binary_dir / "pr"):
            path.touch()
        tasks = state / "tasks"
        fields = [field for bench in ("bfs", "pr")
                  for field in ("gap", bench, "", "1", "120", "4")]
        tasks.write_bytes(("\0".join(fields) + "\0").encode())
        return base, state, (self.root, base, state, gem5, conf, "test", "5489", "", tasks)

    @patch("scripts.run_provenance.gem5_build_info",
           return_value={"gem5_isa": "X86", "gem5_protocol": "MESI_Two_Level"})
    @patch("scripts.run_provenance.gem5_commit", return_value="commit")
    @patch("scripts.run_provenance.subprocess.check_output", return_value="4")
    def test_retry_archives_failed_and_incomplete_without_losing_previous_attempts(self, *_):
        base, state, args = self.retry_fixture()
        failed, incomplete = (base / f"gap_{bench}_c4" for bench in ("bfs", "pr"))
        failed.mkdir()
        incomplete.mkdir()
        (failed / "FAILED").write_text("timeout")
        (failed / "stats.txt").write_text("partial stats")
        (incomplete / "run.json").write_text("partial metadata")
        with self.assertRaisesRegex(ValueError, "not a finished run"):
            preflight(*args)
        self.assertTrue(failed.is_dir())
        self.assertFalse((base / "_failed").exists())
        with contextlib.redirect_stdout(io.StringIO()):
            preflight(*args, retry="1")
            self.assertFalse(failed.exists())
            self.assertFalse(incomplete.exists())
            failed.mkdir()
            (failed / "FAILED").write_text("interrupted")
            preflight(*args, retry="1")
        archived = sorted((base / "_failed").iterdir())
        self.assertEqual(len(archived), 3)
        for path in archived:
            self.assertRegex(path.name, r"gap_(bfs|pr)_c4\.\d{8}T\d{6}\.\d{6}Z$")
        self.assertEqual((archived[0] / "stats.txt").read_text(), "partial stats")
        self.assertEqual((archived[2] / "run.json").read_text(), "partial metadata")
        self.assertTrue((state / "gap_pr_c4.json").is_file())

    @patch("scripts.run_provenance.gem5_build_info",
           return_value={"gem5_isa": "X86", "gem5_protocol": "MESI_Two_Level"})
    @patch("scripts.run_provenance.gem5_commit", return_value="commit")
    @patch("scripts.run_provenance.subprocess.check_output", return_value="4")
    def test_retry_does_not_archive_when_finished_run_mismatches(self, *_):
        base, state, args = self.retry_fixture()
        preflight(*args)
        failed, finished = (base / f"gap_{bench}_c4" for bench in ("bfs", "pr"))
        failed.mkdir()
        (failed / "FAILED").touch()
        finished.mkdir()
        (finished / "DONE").touch()
        (finished / "stats.txt").touch()
        meta = json.loads((state / "gap_pr_c4.json").read_text())
        (finished / "run.json").write_text(json.dumps(dict(meta, seed=42)))
        with self.assertRaisesRegex(ValueError, "seed.*new --variant"):
            preflight(*args, retry="1")
        self.assertTrue(failed.is_dir())
        self.assertTrue((finished / "DONE").is_file())
        self.assertFalse((base / "_failed").exists())

    def test_parser_preserves_run_markers_by_default_and_ignores_archive(self):
        (self.run / "DONE").touch()
        archive = self.root / "_failed"
        archive.mkdir()
        (archive / "DONE").touch()
        (archive / "FAILED").write_text("must not appear")
        script = Path(__file__).resolve().parents[1] / "parse_stats.py"
        command = [sys.executable, str(script), str(self.root)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 1)
        self.assertTrue((self.run / "DONE").is_file())
        self.assertFalse((self.run / "FAILED").exists())
        self.assertEqual((self.root / "failed.txt").read_text(), "")
        self.assertEqual(len((self.root / "summary.csv").read_text().splitlines()), 1)
        second = subprocess.run(command + ["--mark-invalid-runs"], capture_output=True, text=True)
        self.assertEqual(second.returncode, 1)
        self.assertFalse((self.run / "DONE").exists())
        self.assertTrue((self.run / "FAILED").is_file())
        self.assertTrue((archive / "DONE").is_file())

    def test_export_refuses_conflicts_and_identical_content_is_a_noop(self):
        self.make_roi(2)
        with contextlib.redirect_stdout(io.StringIO()):
            target = export_run(self.run, self.data)
            original = target.read_bytes()
            inode = target.stat().st_ino
            export_run(self.run, self.data)
            self.assertEqual(target.stat().st_ino, inode)
            meta = json.loads(self.metadata.read_text())
            for field in ("gem5_sha256", "benchmark_sha256", "seed", "config_sha256", "args", "extra_args"):
                with self.subTest(field=field):
                    self.metadata.write_text(json.dumps(dict(meta, **{field: "different"})))
                    with self.assertRaisesRegex(ValueError, field + ".*--force"):
                        export_run(self.run, self.data)
                    self.assertEqual(target.read_bytes(), original)
            export_run(self.run, self.data, force=True)
        self.assertNotEqual(target.stat().st_ino, inode)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_checker_reports_runner_outliers_per_benchmark_and_missing_jobs(self):
        directory = self.data / "fixture"
        directory.mkdir(parents=True)
        common = dict(suite="gap", benchmark="bfs", cores=4, seed=5489,
                      gem5_sha256="a" * 64, config_sha256="b" * 64,
                      benchmark_sha256="c" * 64, runner="person1",
                      gem5_commit="f" * 40, gem5_isa="X86", gem5_protocol="MESI_Two_Level",
                      args="-g 10 -n 1", extra_args="")

        def write(name, **changes):
            (directory / f"{name}.json").write_text(json.dumps({"run": dict(common, **changes)}))

        write("gap_bfs_c4")
        write("gap_pr_c4", benchmark="pr", runner="person2", benchmark_sha256="d" * 64)
        script = Path(__file__).resolve().parents[1] / "scripts/check_variant.py"
        command = [sys.executable, str(script), str(directory), "--cores", "2", "4"]
        matching = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(matching.returncode, 0)
        self.assertIn("Baseline-v2 coverage: 2/16", matching.stdout)
        self.assertIn("Missing: splash4_FFT_c4", matching.stdout)
        write("gap_bfs_c2", cores=2, runner="person3", benchmark_sha256="e" * 64, seed=42)
        conflict = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("benchmark_sha256 for gap/bfs differs", conflict.stdout)
        self.assertIn("seed differs", conflict.stdout)
        self.assertIn("gap_bfs_c2.json (runner person3)", conflict.stdout)
        self.assertIn("Baseline-v2 coverage: 3/16", conflict.stdout)


    @patch("scripts.run_provenance.subprocess.check_output")
    def test_build_info_records_enabled_isas_and_protocol(self, command):
        command.return_value = ("gem5 version 25.1.0.1\n    USE_X86_ISA = True\n"
                                "    USE_ARM_ISA = True\n    USE_RISCV_ISA = False\n"
                                "    PROTOCOL = MESI_Two_Level\n")
        self.assertEqual(gem5_build_info(Path("/tmp/gem5.opt")),
                         {"gem5_isa": "ARM,X86", "gem5_protocol": "MESI_Two_Level"})
        command.assert_called_once_with(["/tmp/gem5.opt", "--build-info"], text=True)

    def test_export_checker_allows_host_binary_differences_but_rejects_build_and_args(self):
        directory = self.data / "fixture"
        directory.mkdir(parents=True)
        common = dict(suite="gap", benchmark="bfs", cores=4, seed=5489,
                      gem5_sha256="a" * 64, config_sha256="b" * 64,
                      benchmark_sha256="c" * 64, runner="fedora", gem5_commit="f" * 40,
                      gem5_isa="X86", gem5_protocol="MESI_Two_Level", extra_args="",
                      repo_root="/home/fedora/repo", args="/home/fedora/repo/input.txt")
        (directory / "fedora.json").write_text(json.dumps({"run": common}))
        wsl = dict(common, runner="ubuntu-wsl", gem5_sha256="d" * 64,
                   repo_root="/home/wsl/repo", args="/home/wsl/repo/input.txt")
        script = Path(__file__).resolve().parents[1] / "scripts/check_variant.py"
        command = [sys.executable, str(script), str(directory)]

        def check(changes):
            (directory / "wsl.json").write_text(json.dumps({"run": dict(wsl, **changes)}))
            return subprocess.run(command, capture_output=True, text=True)

        result = check({})
        self.assertEqual(result.returncode, 0)
        self.assertIn("INFO: gem5_sha256 differs:", result.stdout)
        self.assertIn("wsl.json (runner ubuntu-wsl)", result.stdout)
        same_runner = check({"runner": "fedora"})
        self.assertEqual(same_runner.returncode, 1)
        self.assertIn("gem5_sha256 differs:", same_runner.stdout)
        self.assertNotIn("INFO: gem5_sha256 differs:", same_runner.stdout)
        for field, value in {"gem5_commit": "e" * 40, "gem5_isa": "ARM",
                             "gem5_protocol": "CHI", "args": "-g 12",
                             "extra_args": "--mem-size 2GiB"}.items():
            with self.subTest(field=field):
                result = check({field: value})
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stdout, rf"{field}( for gap/bfs c4)? differs:")
                self.assertIn("wsl.json (runner ubuntu-wsl)", result.stdout)
        result = check({"gem5_protocol": None})
        self.assertEqual(result.returncode, 1)
        self.assertIn("wsl.json (runner ubuntu-wsl): missing or invalid gem5_protocol", result.stdout)
