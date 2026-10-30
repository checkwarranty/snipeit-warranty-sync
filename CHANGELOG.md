# Changelog

## 1.0.1 — 2026-10-30

- Read the current public B2B API contract, including asynchronous partial results.
- Preserve purchase dates; never invent a missing warranty start date.
- Add an offline CheckWarranty planning mode (`--plan`).
- Build an independently installable CLI package with a unique module name.
- Test installed CLI distributions in CI.

Live dry-run requests may consume API credits. Use sandbox keys and test serials.
