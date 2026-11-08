# DataLab Full-Stack Audit Report

**Project:** DataLab (`C:\Users\Jakeer\Videos\Summer internship\Datalab`)
**Stack:** React 18 + Vite 5 frontend (`frontend/`), FastAPI backend (`backend/`), SQLAlchemy + SQLite/PostgreSQL, Pandas/Scikit-learn ML.
**Audit window:** full audit → live bug fixing → retest → E2E → final verification.
**Date of final assessment:** 2026-11-08

---

## 1. Final Status

# READY WITH LIMITATIONS

The application is functionally complete, builds cleanly, lints cleanly, passes the full backend test suite, and has been exercised end-to-end in a real browser against a live backend.

**Remaining limitations (all documented, none blocking):**

1. **Database engine coverage:** runtime verification used **SQLite only** (isolated test DB under the OS temp dir). PostgreSQL was installed and running, but password authentication for the local `postgres` user could not be established, so PostgreSQL behavior could not be re-verified. The schema was made portable (`JSON().with_variant(JSONB, "postgresql")`), but no PostgreSQL runtime test was executed.
2. **Responsive viewport testing:** the desktop browser tool exposes no viewport-resize/emulation API. Mobile layout was verified by loading the SPA inside a **375px × 812px iframe** (real browser, real CSS, real media queries) and checking for horizontal overflow. All tested routes passed after the fix. True device-level testing is still recommended.
3. **Visual verification:** screenshot capture was unavailable ("Screenshot needs a visible tab"); verification relied on DOM, computed-style, and chart-SVG checks instead.
4. **Bundle size:** production JS chunk is ~750 kB (gzip ~214 kB); build emits a chunk-size warning suggesting future code splitting. Build succeeds.
5. **Frontend automated tests:** none exist (no test runner configured); frontend confidence comes from build, lint, and live browser E2E only.

---

## 2. Test Totals & Coverage

### Backend (pytest, isolated temp SQLite DB + isolated storage dir)

```
cd backend && python -m pytest -q
cd backend && python -m pytest --cov=app --cov-report=term-missing -q
```

| Result | Value |
|---|---|
| Final test run | **124 passed**, 1 warning in **41.26 s** |
| Warnings | 1 (third-party `passlib`/`argon2` DeprecationWarning — library-internal, not app code) |
| Coverage (total) | **92%** |
| Coverage — `app.models` | **100%** |
| Coverage — `app.services.data_io` | **94%** |
| Coverage — `app.services.cleaning_service` | **93%** |
| Coverage — `app.services.ml_service` | **89%** |

Coverage gaps are in rarely-hit error branches (corrupt artifacts, edge-case validation), not in core training/prediction logic.

### Frontend

| Check | Result |
|---|---|
| `npm run build` (vite build) | **SUCCESS** (vite 5.4.21, 2237 modules transformed, built in 16.75 s) |
| `npm run lint` (eslint) | **PASS** (no errors) |
| Live browser E2E | **PASS** (see §6) |
| Mobile-viewport E2E | **PASS after fix** (see §7) |

---

## 3. Bug Fix Log

Each fix was followed by a targeted retest (backend tests and/or live API/browser verification).

| Bug ID | Severity | Area | Root cause | Fix | Retest |
|---|---|---|---|---|---|
| BUG-01 | Critical | Frontend | `src/index.css` (Tailwind entry) was **never imported** in `src/main.jsx`, so no Tailwind styles loaded; charts rendered with **zero height** and the UI was unstyled. | Added `import './index.css'` to `src/main.jsx`. | Re-verified in browser: Tailwind design tokens apply (`bg-brand-600` → `rgb(79,70,229)`), body styling correct, **8 Recharts SVG chart surfaces render**. `npm run build` green. |
| BUG-02 | Critical | Frontend | Vite config/`index.html`/ESM PostCSS/Tailwind configs/favicons were misconfigured → broken production build. | Corrected `vite.config.js`, `index.html`, `tailwind.config.js`, `postcss.config.js`, `src/vite-env.d.ts`, favicon. | `npm run build` **SUCCESS** (2237 modules); `npm run lint` **PASS**. |
| BUG-03 | High | Backend | Grid/flex containers used responsive column classes **without a base column track** (e.g. `grid gap-6 lg:grid-cols-3`), leaving implicit auto columns at mobile widths → **horizontal page overflow** (content stuck out past the viewport). | Added base single-column track (`grid grid-cols-1 gap-6 lg:grid-cols-3`, etc.) across all affected layouts. | Browser E2E at emulated **375px** width: overflow **eliminated** on Dashboard, Datasets, Experiments, Models, Dataset detail, Analysis, Cleaning; no horizontal scroll; cards sized correctly. |
| BUG-04 | High | Backend | Duplicate column names in uploaded CSV/Excel were silently accepted (last-wins on raw header map), corrupting schema inference. | Added strict header validation via `_raw_header()` → returns **400** `{"detail":"Dataset contains duplicate column names"}`. | Live API retest: **400 with expected detail**; client-side validation also surfaced the message. |
| BUG-05 | High | Backend | Dataset delete relied on objects already bulk-deleted → FK/dependency cleanup fragile. | Delete handler captures `file_path` before bulk delete; cascade cleanup verified. | Live E2E: delete → cascade artifacts cleaned; DB state consistent. |
| BUG-06 | Medium | Backend | Cleaning scaling step operated on pandas nullable dtypes without float cast → runtime failure on numeric columns. | Cast to `float` before scaling. | Cleaning E2E retest passed (63→57 rows on fixture). |
| BUG-07 | Medium | Backend | Deprecated FastAPI status code constant (`HTTP_413_REQUEST_ENTITY_TOO_LARGE`) → startup/import incompatibility. | Replaced with current constant. | Backend tests (incl. upload-limit tests) pass. |
| BUG-08 | Medium | Backend | `pandas.to_datetime` emitted warnings; timezone/`format` inference fragility. | Switched to `_to_datetime(format="mixed")`. | Profiling/cleaning tests pass; no warnings from app code. |
| BUG-09 | Medium | Backend | PostgreSQL-only `JSONB` column type broke portability. | `JSON().with_variant(JSONB, "postgresql")`. | Covered by passing backend tests on SQLite; PostgreSQL runtime still NOT TESTED. |
| BUG-10 | Medium | Backend | Auth token handling scattered; security gaps in ownership isolation. | Centralized in `app/security.py` (HTTPBearer + legacy `?token=`); per-resource ownership checks added. | Ownership E2E passed (2nd user → 404 on foreign resources). |

**Bugs found during this final session:** BUG-01 (critical, fixed), BUG-03 (high, fixed — responsive overflow).

---

## 4. Module-Wise Backend Test Summary

| Module | Coverage | Tests |
|---|---|---|
| `app.models` | 100% | Included in 124 passed |
| `app.services.data_io` | 94% | Included in 124 passed |
| `app.services.cleaning_service` | 93% | Included in 124 passed |
| `app.services.ml_service` | 89% | Included in 124 passed |
| **Total** | **92%** | **124 passed, 1 warning** |

Test suites cover: config, database bootstrap, models/schemas, security & auth (register/login/protected routes), dataset upload/preview/versioning/delete, profiling & quality metrics, cleaning operations, experiments & leaderboard, model lifecycle & predictions, ML training/evaluation/prediction.

---

## 5. Build & Lint Results (Frontend, final run after CSS + responsive fixes)

```
> datalab@1.0.0 build
> vite build
vite v5.4.21
building for production...
✓ 2237 modules transformed.
dist/index.html                   0.58 kB
dist/assets/index-*.css           26.38 kB  │ gzip: 5.28 kB
dist/assets/index-*.js           750.39 kB  │ gzip: 213.53 kB
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application ...
✓ built in 16.75s

> datalab@1.0.0 lint
> eslint .
(no output = pass)
```

**Result: BUILD SUCCESS, LINT PASS.**

---

## 6. Live End-to-End (Browser + Live API) Validation

Environment: backend `uvicorn app.main:app --host 127.0.0.1 --port 8000` (isolated SQLite), frontend Vite dev server `127.0.0.1:5173`, E2E storage in `C:\Users\Jakeer\AppData\Local\Temp\opencode\datalab_e2e`.

**Passed flows:**
- Registration, login, protected-route redirect, logout.
- Dataset upload (classification fixture), preview, Analysis Overview/Columns/Charts/Quality, cleaning (63→57 rows, versioned v1, history), classification experiment (logistic + decision tree; recommended logistic; F1 = 0.8333), single prediction (Yes → 99.2%), batch prediction (12 rows).
- Regression upload, regression experiment (linear + ridge; R² = 0.9495 / 0.9490), regression prediction (~250331.398).
- Leaderboard filters/sorting/search, model delete, experiment delete, dataset delete + cascade cleanup.
- Authenticated dataset download from UI.
- Ownership isolation: second user received **404** on all foreign dataset/profiling/experiment/model endpoints and delete attempts; own-resource list empty.

**Live API contract checks:** duplicate headers → `400 {"detail":"Dataset contains duplicate column names"}`; unsupported extension → `400 {"detail":"File extension '.txt' not supported. Allowed: csv, xlsx, xls"}`; client-side validation message shown for unsupported types.

**Console:** no browser console errors on tested routes (only React Router v7 future-flag warnings).

---

## 7. Responsive & Layout Verification (final session)

- Desktop-width checks: no horizontal overflow on tested routes; Tailwind fully active after CSS fix.
- Mobile emulation at **375px** (via in-app iframe): **horizontal overflow detected** before fix (content extending to ~542px on dataset detail page); **zero overflow after fix** on all tested routes (Dashboard, Datasets, Experiments, Models, Dataset detail, Analysis, Cleaning).
- Root cause: responsive-only grid columns without base track (`lg:grid-cols-*` / `sm:grid-cols-*` with no default) → implicit auto-sized columns overflowed container.
- Fix: explicit base single-column tracks added; retest confirmed clean.

---

## 8. ML Validation Summary

- Shared train/test split; full `sklearn.pipeline.Pipeline` per model; preprocessing fit on training data only (no leakage).
- Classification (churn): logistic regression + decision tree; recommended logistic; held-out F1 = **0.8333**.
- Single-feature prediction: **Yes 99.2%**; batch predictions persisted for 12-row fixture.
- Regression (prices): linear + ridge; held-out R² = **0.9495 / 0.9490**; prediction ≈ **250331.398**.
- Optional XGBoost path exercised; algorithm failures isolated; corrupt artifacts rejected; prediction artifacts constrained to `MODELS_DIR`.

---

## 9. Commands Used

```bash
# Backend tests (from backend/)
python -m pytest -q
python -m pytest --cov=app --cov-report=term-missing -q

# Frontend
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm run dev        # http://127.0.0.1:5173 (proxy /api/v1 -> 127.0.0.1:8000)

# Backend
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## 10. Limitations & NOT TESTED Items

- **NOT TESTED:** PostgreSQL runtime behavior (credentials unavailable).
- **NOT TESTED:** Real mobile device/browser viewport behavior (emulated only via iframe).
- **NOT TESTED:** Visual screenshot verification (tooling unavailable; DOM/CSS checks substituted).
- **NOT TESTED:** Frontend unit tests (none configured).
- Existing root-level stubs (`test_api.py` with wrong hardcoded path, `test_version.py` printing SQLAlchemy version) were **not** treated as part of the audited suite.

---

## 11. Conclusion

Critical and high-severity defects found during the audit (unstyled frontend, responsive horizontal overflow, duplicate-header handling, delete/cleaning/scaling issues) were fixed, retested, and re-verified. The full backend suite (124 tests) passes, coverage is 92%, frontend builds and lints cleanly, and complete browser E2E plus ML validation flows pass.

**Final status: READY WITH LIMITATIONS** — pending only the items listed in §10.
