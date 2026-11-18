import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.export_run import export_run
from scripts.merge_summaries import merge_summaries
from scripts.run_provenance import GUARD_FIELDS, check_existing
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
