# Tenstorrent fixtures

The Wormhole fixtures are captured `tt-smi -s` snapshots used by the existing
Tenstorrent tests.

The Blackhole Galaxy fixture is a captured `tt-smi -s` snapshot from a 32-chip
Galaxy Blackhole host.

The Blackhole PCIe fixtures are source-derived compatibility fixtures:

- `blackhole_boards.json` covers `tt-smi` Blackhole board names and P300
  same-board dual-MMIO behavior. Board names are based on
  `tt_smi/utils.py::get_board_type` and UMD board type mappings.
- `blackhole_8xp150.json` is derived from UMD's
  `blackhole_8xP150.yaml` cluster descriptor. The board IDs and PCI bus IDs are
  from that descriptor; the `p150b` board name follows the UPI mapping used by
  `tt-smi`.
These fixtures are not substitutes for live hardware smoke tests. They preserve
captured `tt-smi` JSON shapes and source-derived UMD topology cases.
