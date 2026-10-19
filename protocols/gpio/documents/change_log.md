# SniffWorks GPIO sniffer — Change Log
<!-- v0.1 -->

Versioning rules: every file carries a version tag on line 2, below the reserved first line (shebang, or the Markdown title). New files start at v0.1; any change bumps the minor; only the owner declares a major. Files version independently. Entries are chronological, newest last.

---

## 2026-10-19 — Baseline: sub-project created

| File | Version | Change |
|---|---|---|
| CLAUDE.md | 1.0 | Working agreement: decisions G-01..G-04, findings, open questions |
| README.md | v0.1 | Purpose and layout |
| documents/requirements.md | v0.1 | Draft requirements GPIO-R01..R11 (owner vs proposed marked) |
| documents/change_log.md | v0.1 | This file |
| core/, ui/, schema/, tests/, tools/, documents/user_guides/ | — | Empty folders (`.gitkeep`) |

Why: GPIO is the second SniffWorks protocol (root SW-05), created in the target layout the owner chose (root SW-14). No code yet; the event model and CSV columns wait for the root open questions.
