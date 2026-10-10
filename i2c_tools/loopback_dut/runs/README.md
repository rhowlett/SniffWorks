# loopback_dut/runs
<!-- v0.1 -->

Rig artefacts of the loopback harness (inputs to `tests/test_loopback_capture.py`):

| File | Written by |
|---|---|
| `expected.json` | `host/loopback_run.py --port <DUT>` (ground truth from the DUT) |
| `ion_capture.csv` | sniffer_ion Export CSV (C031, fw ≥ 1.3), captured during the run |
| `ad2_capture.csv` | sniffer_ad2 Export CSV, captured during the run |
| `loopback_report_<path>.md` | `tests/test_loopback_capture.py` / `host/loopback_compare.py` |

Keep the files from a run that is cited as evidence in a phase review; they are the evidence.
