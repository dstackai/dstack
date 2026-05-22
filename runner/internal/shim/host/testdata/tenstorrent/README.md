# Tenstorrent fixtures

The Wormhole fixtures are captured `tt-smi -s` snapshots used by the existing
Tenstorrent tests.

The Blackhole fixtures are source-derived compatibility fixtures:

- `blackhole_boards.json` covers `tt-smi` Blackhole board names and P300
  same-board dual-MMIO behavior. Board names are based on
  `tt_smi/utils.py::get_board_type` and UMD board type mappings.
- `blackhole_8xp150.json` is derived from UMD's
  `blackhole_8xP150.yaml` cluster descriptor. The board IDs and PCI bus IDs are
  from that descriptor; the `p150b` board name follows the UPI mapping used by
  `tt-smi`.
- `blackhole_galaxy.json` is derived from the Blackhole Galaxy example in the
  `tt-smi` README, which shows a 32-ASIC Galaxy reporting `tt-galaxy-bh`.

These fixtures are not substitutes for live hardware smoke tests. They preserve
the `tt-smi` JSON shapes and UMD topology cases that we can verify from source.
