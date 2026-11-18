import json
from pathlib import Path
import tempfile
import unittest

from scripts.staged_workload import experiment_layout, resolve_args


class StagingTests(unittest.TestCase):
    def test_variant_and_checkout_do_not_change_guest_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            descriptions = []
            for checkout, variant in (("alice's repo", "baseline"), ("bob", "candidate")):
                repo = Path(directory) / checkout
                out = repo / "runs" / variant
                args = resolve_args("-p2 {repo}/data/scene.env < {repo}/input", repo)
                guest = experiment_layout("splash4", "RAYTRACE", "2", args, out)
                descriptions.append(json.dumps(guest).encode())
            self.assertEqual(*descriptions)
            cwd = "/tmp/cmm-run/splash4_RAYTRACE_c2"
            self.assertEqual(guest["cwd"], cwd)
            self.assertEqual(guest["argv"], [cwd + "/bin/RAYTRACE", "-p2", cwd + "/args/1/scene.env"])
            self.assertEqual(guest["stdin"], cwd + "/stdin.in")
            self.assertIn(cwd + "/inputs/teapot.geo", guest["staged_inputs"])
            self.assertEqual(guest["env"], ["OMP_NUM_THREADS=2", "OMP_WAIT_POLICY=PASSIVE", "GOMP_SPINCOUNT=1"])
