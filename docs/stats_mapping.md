# ROI coherence stat mapping

Source inspected: `results/baseline/splash4_OCEAN-CONT_c4/stats.txt`, first
`Begin Simulation Statistics` / `End Simulation Statistics` block only.
All names below have the exact prefix `board.cache_hierarchy.ruby_system.`.
No simulation was run to produce these additions.

## Selected columns

Four base metrics and four normalized columns are appended after all existing columns.

| CSV column | Exact source suffix(es) | Reason and meaning | OCEAN-CONT c4 ROI count |
| --- | --- | --- | ---: |
| `L1_invalidations` | `L1Cache_Controller.Inv` | Incoming invalidation events at L1 controllers; does not imply every event invalidated a valid data line. | 27993 |
| `L1_upgrades` | `L1Cache_Controller.S.Store` | Store event in Shared state: a direct L1 ownership-upgrade indicator. | 2575 |
| `L1_fwd_requests` | `L1Cache_Controller.Fwd_GETS`, `L1Cache_Controller.Fwd_GETX` | Forwarded shared/exclusive requests handled by L1 controllers. Sum both event vectors once. | 13674 |
| `L1_outgoing_msgs` | `l1_controllers{core}.requestFromL1Cache.m_msg_count`, `l1_controllers{core}.responseFromL1Cache.m_msg_count`, `l1_controllers{core}.unblockFromL1Cache.m_msg_count` | Outgoing L1 coherence traffic across request, response, and unblock buffers; includes data responses and writebacks. | See summary.csv |

The event counters are pipe-delimited vectors with one count per core, followed
by percentage and cumulative-percentage fields in each cell. Sum only the counts
across exactly the configured number of L1 controllers (tested through eight).
The accompanying `::total` scalars and state-specific breakdowns are alternatives,
not additional events; they must not be added to the vectors.
The per-controller message counters sum across all configured cores.
These counters cover the whole L1 controller, including instruction traffic;
they are not L1D-only counters.

Each metric also has `<column>_per_kinst = 1000 * count / instructions`, using the
existing sum of committed per-core instructions over the same ROI blocks.
A missing source component in any core or selected frame leaves the entire metric
and its normalized value empty. A measured zero remains zero. With zero committed
instructions, the raw counter remains available and the normalized cell is empty.
Malformed present counts fail validation (finite, nonnegative integers required).

ROI selection is unchanged: the first block normally, the first three frame blocks
for VOLREND and VOLREND-NPL, never their automatic exit block. Existing non-ROI
runs retain their existing single-block policy.

## Other candidates and exclusions

- `L2Cache_Controller.L1_GETS::total` (3533744),
  `L2Cache_Controller.L1_GETX::total` (597638), and
  `L2Cache_Controller.L1_UPGRADE::total` (2608) count events handled at L2.
  GETX includes ownership requests beyond stores to Shared lines. L2 upgrade
  events are a different observation point from L1 `S.Store` (2575).
- `L2Cache_Controller.L1_PUTX::total` (3494583) and
  `L2Cache_Controller.L1_PUTX_old::total` (159) expose writeback-related L2 events.
  They are not per-core L1 counters. Their state breakdowns overlap their totals.
- `network.msg_count.Control` (8701106),
  `network.msg_count.Request_Control` (83334),
  `network.msg_count.Response_Data` (8892576),
  `network.msg_count.Response_Control` (14358988),
  `network.msg_count.Writeback_Data` (1552470), and
  `network.msg_count.Writeback_Control` (5436360) provide message-type counts.
  These are network-wide traffic counters, not per-core L1 events. Router and
  throttle counters also exist, with `msg_count.Control::0`,
  `msg_count.Request_Control::2`, `msg_count.Response_Data::1`,
  `msg_count.Response_Control::1`, `msg_count.Response_Control::2`, `msg_count.Writeback_Data::0`, and
  `msg_count.Writeback_Control::0` suffixes where present. Adding network, router,
  and throttle counts would mix overlapping observations of routed traffic.
- `mandatoryQueue.m_msg_count` counts processor-side requests rather than outgoing
  coherence messages. `requestToL1Cache` and `responseToL1Cache` are incoming
  buffers and are excluded from `L1_outgoing_msgs`.

## Exact candidate inventory from the inspected ROI

The following names are copied from the real dump, including event totals and
state breakdowns. `l1_controllers0` represents the buffer names also observed on
controllers 1, 2, and 3. Prefix each line with
`board.cache_hierarchy.ruby_system.` to obtain the full stat name.

```text
L1Cache_Controller.Inv
L1Cache_Controller.Inv::total
L1Cache_Controller.Fwd_GETX
L1Cache_Controller.Fwd_GETX::total
L1Cache_Controller.Fwd_GETS
L1Cache_Controller.Fwd_GETS::total
L1Cache_Controller.NP.Inv
L1Cache_Controller.NP.Inv::total
L1Cache_Controller.S.Store
L1Cache_Controller.S.Store::total
L1Cache_Controller.S.Inv
L1Cache_Controller.S.Inv::total
L1Cache_Controller.E.Fwd_GETX
L1Cache_Controller.E.Fwd_GETX::total
L1Cache_Controller.E.Fwd_GETS
L1Cache_Controller.E.Fwd_GETS::total
L1Cache_Controller.M.Fwd_GETX
L1Cache_Controller.M.Fwd_GETX::total
L1Cache_Controller.M.Fwd_GETS
L1Cache_Controller.M.Fwd_GETS::total
L1Cache_Controller.IS.Inv
L1Cache_Controller.IS.Inv::total
L1Cache_Controller.IM.Inv
L1Cache_Controller.IM.Inv::total
L1Cache_Controller.SM.Inv
L1Cache_Controller.SM.Inv::total
L1Cache_Controller.M_I.Fwd_GETX
L1Cache_Controller.M_I.Fwd_GETX::total
L1Cache_Controller.M_I.Fwd_GETS
L1Cache_Controller.M_I.Fwd_GETS::total
L2Cache_Controller.L1_GETS
L2Cache_Controller.L1_GETS::total
L2Cache_Controller.L1_GETX
L2Cache_Controller.L1_GETX::total
L2Cache_Controller.L1_UPGRADE
L2Cache_Controller.L1_UPGRADE::total
L2Cache_Controller.L1_PUTX
L2Cache_Controller.L1_PUTX::total
L2Cache_Controller.L1_PUTX_old
L2Cache_Controller.L1_PUTX_old::total
L2Cache_Controller.NP.L1_GETS
L2Cache_Controller.NP.L1_GETS::total
L2Cache_Controller.NP.L1_GETX
L2Cache_Controller.NP.L1_GETX::total
L2Cache_Controller.SS.L1_GETS
L2Cache_Controller.SS.L1_GETS::total
L2Cache_Controller.SS.L1_GETX
L2Cache_Controller.SS.L1_GETX::total
L2Cache_Controller.SS.L1_UPGRADE
L2Cache_Controller.SS.L1_UPGRADE::total
L2Cache_Controller.SS.L1_PUTX
L2Cache_Controller.SS.L1_PUTX::total
L2Cache_Controller.M.L1_GETS
L2Cache_Controller.M.L1_GETS::total
L2Cache_Controller.M.L1_GETX
L2Cache_Controller.M.L1_GETX::total
L2Cache_Controller.MT.L1_GETS
L2Cache_Controller.MT.L1_GETS::total
L2Cache_Controller.MT.L1_GETX
L2Cache_Controller.MT.L1_GETX::total
L2Cache_Controller.MT.L1_PUTX
L2Cache_Controller.MT.L1_PUTX::total
L2Cache_Controller.MT.L1_PUTX_old
L2Cache_Controller.MT.L1_PUTX_old::total
L2Cache_Controller.ISS.L1_GETS
L2Cache_Controller.ISS.L1_GETS::total
L2Cache_Controller.ISS.L1_GETX
L2Cache_Controller.ISS.L1_GETX::total
L2Cache_Controller.IS.L1_GETS
L2Cache_Controller.IS.L1_GETS::total
L2Cache_Controller.IM.L1_GETS
L2Cache_Controller.IM.L1_GETS::total
L2Cache_Controller.IM.L1_GETX
L2Cache_Controller.IM.L1_GETX::total
L2Cache_Controller.SS_MB.L1_GETS
L2Cache_Controller.SS_MB.L1_GETS::total
L2Cache_Controller.SS_MB.L1_GETX
L2Cache_Controller.SS_MB.L1_GETX::total
L2Cache_Controller.SS_MB.L1_UPGRADE
L2Cache_Controller.SS_MB.L1_UPGRADE::total
L2Cache_Controller.MT_MB.L1_GETS
L2Cache_Controller.MT_MB.L1_GETS::total
L2Cache_Controller.MT_MB.L1_GETX
L2Cache_Controller.MT_MB.L1_GETX::total
L2Cache_Controller.MT_MB.L1_PUTX
L2Cache_Controller.MT_MB.L1_PUTX::total
L2Cache_Controller.MT_IIB.L1_GETS
L2Cache_Controller.MT_IIB.L1_GETS::total
L2Cache_Controller.MT_IIB.L1_GETX
L2Cache_Controller.MT_IIB.L1_GETX::total
L2Cache_Controller.MT_IIB.L1_PUTX
L2Cache_Controller.MT_IIB.L1_PUTX::total
L2Cache_Controller.MT_SB.L1_GETS
L2Cache_Controller.MT_SB.L1_GETS::total
L2Cache_Controller.MT_SB.L1_GETX
L2Cache_Controller.MT_SB.L1_GETX::total
L2Cache_Controller.MT_SB.L1_UPGRADE
L2Cache_Controller.MT_SB.L1_UPGRADE::total
l1_controllers0.mandatoryQueue.m_msg_count
l1_controllers0.requestFromL1Cache.m_msg_count
l1_controllers0.requestToL1Cache.m_msg_count
l1_controllers0.responseFromL1Cache.m_msg_count
l1_controllers0.responseToL1Cache.m_msg_count
l1_controllers0.unblockFromL1Cache.m_msg_count
network.msg_count.Control
network.msg_count.Request_Control
network.msg_count.Response_Data
network.msg_count.Response_Control
network.msg_count.Writeback_Data
network.msg_count.Writeback_Control
```
