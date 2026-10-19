# SniffWorks probe firmware — Change Log
<!-- v0.1 -->

Versioning rules: every source file carries a version tag on line 2; new files start at v0.1; any change bumps the minor; only the owner declares a major. Files in CubeMX-generated trees keep their tag inside a USER CODE region. Entries are chronological, newest last.

---

## 2026-10-19 — Baseline: firmware tree created

| File | Version | Change |
|---|---|---|
| firmware/README.md | v0.1 | Tree layout and target naming |
| firmware/docs/build_and_flash.md | v0.1 | Placeholder: points to the proven C031 procedure in i2c_tools |
| firmware/docs/change_log.md | v0.1 | This file |
| common/, targets/stm32c031c6-nucleo/, targets/stm32h723zg-nucleo/ | — | Empty folders (`.gitkeep`) |

Why: one firmware source tree with shared code, per-board targets and build configurations (root SW-04), in the layout the owner chose (root SW-14).
