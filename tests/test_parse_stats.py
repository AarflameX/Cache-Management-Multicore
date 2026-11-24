"""Small synthetic ROI dumps: no simulator or benchmark binaries required."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from parse_stats import COHERENCE_FIELDS, parse_run

PREFIX = 'board.cache_hierarchy.ruby_system.'


def block(cores=2, banks=(0, 1), multiplier=1, zero_core=None, prefetch=True):
    values = {'simSeconds': str(0.01 * multiplier)}
    for core in range(cores):
        base = f'{PREFIX}l1_controllers{core}'
        values[f'{base}.L1Dcache.m_demand_hits'] = (0 if core == zero_core else 90 * (core + 1)) * multiplier
        values[f'{base}.L1Dcache.m_demand_misses'] = (0 if core == zero_core else 10 * (core + 1)) * multiplier
        values[f'board.processor.cores{core}.core.commitStats0.numInsts'] = 1000 * (core + 1) * multiplier
        if prefetch:
            values[f'{base}.prefetcher.RubyPrefetcher.numHits'] = 3 * (core + 1) * multiplier
            values[f'{base}.prefetcher.RubyPrefetcher.numMissedPrefetchedBlocks'] = (core + 1) * multiplier
    for bank in banks:
        base = f'{PREFIX}l2_controllers{bank}.L2cache'
        values[f'{base}.m_demand_hits'] = 20 * (bank + 1) * multiplier
        values[f'{base}.m_demand_misses'] = 5 * (bank + 1) * multiplier
    return values


def coherence_block(multiplier=1, cores=2):
    values = block(cores=cores, multiplier=multiplier)
    snippet = Path(__file__).with_name('fixtures') / 'coherence.txt'
    for line in snippet.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, value = line.split(None, 1)
        if '|' in value:
            counts = [int(cell.split()[0]) for cell in value.split('|')[1:]]
            counts = (counts * 4)[:cores]
            value = '| ' + ' | '.join(f'{count * multiplier} 0.00% 0.00%' for count in counts)
        else:
            value = int(value) * multiplier
        values[name] = value
    for core in range(2, cores):
        for buffer in ('requestFromL1Cache', 'responseFromL1Cache', 'unblockFromL1Cache'):
            values[f'{PREFIX}l1_controllers{core}.{buffer}.m_msg_count'] = 10 * multiplier
    return values


class ParseStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)

    def fixture(self, blocks, benchmark='bfs', cores=2, **metadata):
        meta = dict(suite='gap', benchmark=benchmark, cores=cores, variant='fixture', roi=1)
        meta.update(metadata)
        (self.run / 'run.json').write_text(json.dumps(meta))
        text = ''
        for values in blocks:
            text += '---------- Begin Simulation Statistics ----------\n'
            text += ''.join(f'{key} {value}\n' for key, value in values.items())
            text += '---------- End Simulation Statistics ----------\n'
        (self.run / 'stats.txt').write_text(text)
        return parse_run(self.run)

    def test_normal_gap_uses_first_block(self):
        row = self.fixture([block(), block(multiplier=99)], wall_seconds=2.5)
        self.assertEqual(row['L1D_hits'], 270)
        self.assertEqual(row['L1D_misses'], 30)
        self.assertEqual(row['L1D_accesses'], 300)
        self.assertEqual(row['L1D_miss_rate'], 0.1)
        self.assertEqual(row['L1D_imbalance'], 2)
        self.assertEqual(row['L2_hits'], 60)
        self.assertEqual(row['L2_misses'], 15)
        self.assertEqual(row['instructions'], 3000)
        self.assertEqual(row['L1D_MPKI'], 10)
        self.assertEqual(row['L2_MPKI'], 5)
        self.assertEqual(row['L1D_prefetch_hits'], 9)
        self.assertEqual(row['L1D_prefetch_misses'], 3)
        self.assertEqual(row['wall_seconds'], 2.5)
        self.assertNotIn('core2_L1D_accesses', row)

    def test_calibration_metrics_use_roi_and_host_rss(self):
        first = block()
        first.update(simTicks=10_000_000_001, simFreq=10**12)
        for core in range(2):
            first[f"board.processor.cores{core}.core.numCycles"] = 2000
        first[PREFIX + "L1Cache_Controller.L1_Replacement::total"] = 7
        first[PREFIX + "L2Cache_Controller.L2_Replacement::total"] = 0
        first[PREFIX + "L2Cache_Controller.L2_Replacement_clean::total"] = 11
        (self.run / "peak_rss_kib.txt").write_text("12345\n")
        row = self.fixture([first, block()])
        self.assertEqual(row["simTicks"], 10_000_000_001)
        self.assertAlmostEqual(row["sim_seconds_from_ticks"], 0.010000000001)
        self.assertEqual(row["IPC"], 0.75)
        self.assertEqual(row["L1_replacements"], 7)
        self.assertEqual(row["L2_replacements"], 11)
        self.assertEqual(row["peak_rss_kib"], 12345)

    def test_volrend_sums_three_frames_ignores_exit(self):
        for name in ('VOLREND', 'volrend', 'VOLREND-NPL', 'volrend-npl'):
            with self.subTest(benchmark=name):
                row = self.fixture([block(multiplier=x) for x in (1, 2, 3, 99)], benchmark=name)
                self.assertEqual(row['L1D_accesses'], 1800)
                self.assertEqual(row['L2_misses'], 90)
                self.assertEqual(row['instructions'], 18000)
                self.assertAlmostEqual(row['simSeconds'], 0.06)
                self.assertEqual(row['L1D_prefetch_hits'], 54)
                self.assertEqual(row['L1D_MPKI'], 10)

    def test_wrong_block_count(self):
        with self.assertRaisesRegex(ValueError, 'expected 4 statistics blocks, found 2'):
            self.fixture([block(), block()], benchmark='VOLREND')
        with self.assertRaisesRegex(ValueError, 'expected 2 statistics blocks, found 1'):
            self.fixture([block()])

    def test_missing_stat_fails_cli(self):
        values = block()
        del values[f'{PREFIX}l1_controllers1.L1Dcache.m_demand_misses']
        with self.assertRaisesRegex(ValueError, 'missing expected stat.*m_demand_misses'):
            self.fixture([values, block()])
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'parse_stats.py'),
                                 '--validate', str(self.run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('ERROR:', result.stderr)
        self.assertIn('missing expected stat', result.stderr)

    def test_zero_access_core_warns_without_failure(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            row = self.fixture([block(zero_core=1), block()])
        self.assertIn('WARNING:', stderr.getvalue())
        self.assertIn('core1 has zero L1D accesses', stderr.getvalue())
        self.assertEqual(row['L1D_imbalance'], '')
        self.assertEqual(row['core1_L1D_accesses'], 0)
        self.assertEqual(row['core1_L1D_miss_rate'], 0)
        self.assertEqual(row['L1D_accesses'], 100)

    def test_four_cores_and_all_noncontiguous_banks(self):
        row = self.fixture([block(cores=4, banks=(0, 2, 4, 7)), block()], cores=4)
        self.assertEqual(row['L1D_accesses'], 1000)
        self.assertEqual(row['instructions'], 10000)
        self.assertEqual(row['core3_L1D_accesses'], 400)
        self.assertEqual(row['L1D_imbalance'], 4)
        self.assertEqual(row['L2_hits'], 340)
        self.assertEqual(row['L2_misses'], 85)
        self.assertEqual(row['L2_accesses'], 425)

    def test_l1_indices_must_match_cores_exactly(self):
        for count in (1, 3):
            with self.subTest(found=count), self.assertRaisesRegex(ValueError, 'L1 controller indices'):
                self.fixture([block(cores=count), block()], cores=2)

    def test_at_least_one_l2_bank_required(self):
        with self.assertRaisesRegex(ValueError, 'no L2 banks found'):
            self.fixture([block(banks=()), block()])

    def test_l2_bank_set_must_match_across_frames(self):
        with self.assertRaisesRegex(ValueError, 'L2 bank indices changed'):
            self.fixture([block(), block(banks=(0,)), block(), block()], benchmark='VOLREND')

    def test_legacy_metadata_and_absent_prefetch_are_blank(self):
        row = self.fixture([block(prefetch=False), block()])
        self.assertEqual(row['wall_seconds'], '')
        self.assertEqual(row['L1D_prefetch_hits'], '')
        self.assertEqual(row['L1D_prefetch_misses'], '')

    def test_partial_prefetch_fails_instead_of_undercounting(self):
        values = block()
        del values[f'{PREFIX}l1_controllers1.prefetcher.RubyPrefetcher.numHits']
        with self.assertRaisesRegex(ValueError, 'missing expected stat.*numHits'):
            self.fixture([values, block()])

    def test_missing_committed_instructions_fails(self):
        values = block()
        del values['board.processor.cores1.core.commitStats0.numInsts']
        with self.assertRaisesRegex(ValueError, 'missing expected stat.*commitStats0.numInsts'):
            self.fixture([values, block()])

    def test_zero_instructions_guard_mpki(self):
        values = block()
        for core in range(2):
            values[f'board.processor.cores{core}.core.commitStats0.numInsts'] = 0
        row = self.fixture([values, block()])
        self.assertEqual(row['instructions'], 0)
        self.assertEqual(row['L1D_MPKI'], '')
        self.assertEqual(row['L2_MPKI'], '')

    def test_roi_type_is_bool_or_int(self):
        for roi in (True, 1):
            with self.subTest(roi=roi):
                self.assertEqual(self.fixture([block(), block()], roi=roi)['L1D_accesses'], 300)
        with self.assertRaisesRegex(ValueError, 'roi must be a bool or integer'):
            self.fixture([block(), block()], roi='1')

    def test_coherence_first_roi_and_normalization(self):
        exit_block = coherence_block(99)
        exit_block[f'{PREFIX}L1Cache_Controller.Inv'] = '| malformed |'
        row = self.fixture([coherence_block(), exit_block])
        for field, expected in zip(COHERENCE_FIELDS, (5, 4, 15, 210)):
            self.assertEqual(row[field], expected)
            self.assertAlmostEqual(row[field + '_per_kinst'], expected / 3)

    def test_coherence_three_frames_never_exit(self):
        for benchmark in ('VOLREND', 'VOLREND-NPL'):
            row = self.fixture([coherence_block(x) for x in (1, 2, 3, 99)], benchmark=benchmark)
            for field, expected in zip(COHERENCE_FIELDS, (30, 24, 90, 1260)):
                self.assertEqual(row[field], expected)
                self.assertAlmostEqual(row[field + '_per_kinst'], expected / 18)

    def test_coherence_missing_components_or_frames_are_blank(self):
        for name, field in (
            (f'{PREFIX}L1Cache_Controller.Inv', 'L1_invalidations'),
            (f'{PREFIX}L1Cache_Controller.Fwd_GETX', 'L1_fwd_requests'),
            (f'{PREFIX}l1_controllers1.requestFromL1Cache.m_msg_count', 'L1_outgoing_msgs'),
        ):
            values = coherence_block()
            del values[name]
            row = self.fixture([coherence_block(), values, coherence_block(), coherence_block()], benchmark='VOLREND')
            self.assertEqual(row[field], '')
            self.assertEqual(row[field + '_per_kinst'], '')
        row = self.fixture([block(), coherence_block()])
        for field in COHERENCE_FIELDS:
            self.assertEqual(row[field], '')
            self.assertEqual(row[field + '_per_kinst'], '')

    def test_coherence_eight_cores(self):
        row = self.fixture([coherence_block(cores=8), block()], cores=8)
        self.assertEqual(row['L1_invalidations'], 20)
        self.assertEqual(row['L1_upgrades'], 16)
        self.assertEqual(row['L1_fwd_requests'], 60)
        self.assertEqual(row['L1_outgoing_msgs'], 390)

    def test_coherence_zero_counts_and_zero_instructions(self):
        with contextlib.redirect_stderr(io.StringIO()):
            row = self.fixture([coherence_block(0), coherence_block()], roi=1)
        for field in COHERENCE_FIELDS:
            self.assertEqual(row[field], 0)
            self.assertEqual(row[field + '_per_kinst'], '')
        values = coherence_block()
        for name in values:
            if name.startswith(f'{PREFIX}L1Cache_Controller.'):
                values[name] = '| 0 0% 0% | 0 0% 0%' if '::' not in name else 0
        row = self.fixture([values, block()])
        self.assertEqual(row['L1_invalidations_per_kinst'], 0)

    def test_coherence_invalid_vector_counts(self):
        for value in ('| 1 0% 0%', '| -1 0% 0% | 2 0% 0%',
                      '| nan 0% 0% | 2 0% 0%', '| 1.5 0% 0% | 2 0% 0%'):
            values = coherence_block()
            values[f'{PREFIX}L1Cache_Controller.Inv'] = value
            with self.assertRaises(ValueError):
                self.fixture([values, block()])


if __name__ == '__main__':
    unittest.main()
