"""
version.py  [v1.3]
Single source of truth for the ion_i2c_tool PROJECT version.

Set to major 1.0 on 2026-07-09 (project conventions): the suite at this
point comprises the four applications (sniffer_ion / sniffer_ad2 /
i2c_replay / decoder_editor, plus theme_editor), decoder schema v4 with the
BQ76905 and full BQ25731 decoders, the Registers tabs with v1.1 coloring,
framework-wide tab pop-out, and probe firmware 1.1 (deferred-emit)
(1.3.0: probe firmware 1.2, zero-copy ring)
(1.4.0: probe firmware 1.3 per-transaction SCL measurement; capture CSV v2
adds the SCL (Hz) column, v1 files still load)
(1.5.0: probe firmware 1.4 sampler diagnostics in STATUS, table CRC, upkeep
deferred while a transaction is open; tools/ion_capture.py)
(1.6.0: probe firmware 1.6 edge-interrupt sampling (review B30 fixed), host
commands by DMA (fw 1.5); sniffer_ion / sniffer_ad2 Device tabs harmonized
with compact icon buttons; Phase 1 loopback DUT closed).

Component versions elsewhere, on purpose:
  * probe firmware: FW_VERSION_MAJOR/MINOR in
    embedded/sniffer_nucleoC0_fw/Core/Inc/sniffer_config.h (reported over
    HELLO; shown in the app status bar) — hardware release cadence differs.
  * decoder JSON format: "version" in each decoder file / SCHEMA_VERSION in
    core/decode_schema.py — a data format, not the product.
  * per-file [vX.Y] tags mark individual module revisions.

Bump rules: MAJOR for breaking changes to file formats, the frame
protocol, or the decoder schema; MINOR for features; PATCH for fixes.
"""
PROJECT_VERSION = "1.6.0"
