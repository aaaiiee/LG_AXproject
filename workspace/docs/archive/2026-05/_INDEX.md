# Archive — 2026-05

| Feature | Status | Match Rate | Duration | Archived On | Location |
|---|:-:|:-:|:-:|:-:|---|
| [deploy-guide](deploy-guide/) | Completed | 97% | 1 day (2026-05-22) | 2026-05-22 | `deploy-guide/` |
| [coupang-live](coupang-live/) | **Deferred** | — | spike only (2026-05-22) | 2026-05-22 | `coupang-live/` |

## Notes

- **deploy-guide** — Korean documentation feature: README + RUNBOOK + DEPLOY + bootstrap.sh + .env.example. Smoke verified, 169/169 pytest still green, G1 fixed (placeholder→empty) before archive. Summary preserved in `.pdca-status.json` (FR-04 mode).

- **coupang-live** — **Deferred (infrastructure blocker)**. Spike confirmed Akamai Bot Manager blocks crawl4ai default headless Chromium (TLS fingerprint + `navigator.webdriver` detection). Path A not viable. See `coupang-live.spike.md` for full findings + 5 alternatives. Decision: replaced by new `naver-shopping` cycle using official Naver Shopping API (25k requests/day free quota).
