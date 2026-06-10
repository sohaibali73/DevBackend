# Azure Migration Plan — Supabase + Vercel + Railway → Azure

> **IMPLEMENTATION STATUS (done in-repo):** Code migration is complete.
> Decisions taken: **self-hosted JWT** auth (not Entra — runs with zero external
> setup; reversible later), **in-process DB shim** (not a PostgREST sidecar),
> **Container Apps** for both apps. See `infra/README.md` for the deploy runbook.
> Remaining = provisioning (provider registration by an admin), then build/push
> images → `az deployment group create` → `apply_migrations.py`.

**Goal:** Move the entire stack to Azure. Decommission Supabase (DB + Auth + Storage), Vercel (frontend host), and Railway (backend host).

**Decisions locked in:**
- **Auth:** Azure **Entra External ID** (CIAM / B2C) replaces Supabase Auth.
- **Frontend host:** Azure **Container Apps** running Next.js in Node standalone mode.
- **Backend host:** Azure **Container Apps** (already containerized).

**Verified subscription state (2026-06-08):**
- Subscription `PFM-AI-Apps-Dev` (`a1eac51c-…`), tenant `b6a9681f-…`, single resource group **`PFM-RG-AI_Apps-Dev`** in **`eastus`**.
- Resource group is **empty** — clean slate, everything below is greenfield provisioning.
- **No Redis Cache, Key Vault, or Container Registry** appear in the tooling palette — the plan is designed to **not require them** (workarounds below). They remain optional upgrades if permissions allow.
- **Web PubSub** and **Managed Identities** are available — used for WebSockets and passwordless Blob/Postgres access respectively.
- ⚠️ **Entra External ID** is a *directory/tenant* resource, not a resource-group resource — it won't show in the panel. Creating a CIAM tenant needs directory-level permission. **Confirm you can create one before committing to Entra auth**; if not, fall back to self-hosted JWT (see §4.2 note).

---

## 1. Target Azure architecture

| Concern | Today | Azure target |
|---|---|---|
| Backend runtime | Railway (nixpacks, `python main.py`) | **Azure Container Apps** (Docker), min-replicas = 1 |
| Frontend runtime | Vercel (edge + serverless) | **Azure Container Apps** (Next.js standalone, `next start`) |
| Container images | Railway build | **`az containerapp up --source`** (auto-creates ACR) or **ghcr.io** — no manual ACR node needed |
| Postgres | Supabase Postgres | **Azure Database for PostgreSQL — Flexible Server** |
| PostgREST (`.table()`) | Supabase PostgREST | **Self-hosted PostgREST sidecar** OR in-process shim (see §4.1) |
| Auth | Supabase Auth (HS256 JWT) | **Entra External ID** (RS256 JWT via JWKS) — *pending tenant-permission check* |
| Object storage | Supabase Storage (4 buckets) | **Azure Blob Storage** (4 containers), accessed via **Managed Identity** |
| Persistent volume (`/data`) | Railway volume | **Azure Files** share mounted on the Container App |
| Cache | Redis (Railway) | **Drop Redis** → in-process LRU fallback (already built into `core/cache.py`); single replica makes this lossless. *(Optional: Container Apps Redis add-on if cross-instance cache ever needed.)* |
| Secrets | Railway/Vercel env vars | **Container App secrets** (native, no Key Vault required). *(Optional: Key Vault later.)* |
| WebSockets | Railway ingress | **Container Apps ingress** (native WS) — *or* **Web PubSub** (available) if you want a managed WS plane |
| CI/CD | Vercel + Railway auto-deploy | **GitHub Actions** → `containerapp up` / registry → Container Apps |
| Email (password reset) | SMTP (Gmail) | Handled by Entra hosted flows (SMTP no longer needed for reset) |

The resource group `PFM-RG-AI_Apps-Dev` will hold: 2 Container Apps + a Container Apps Environment, PostgreSQL Flexible Server, a Storage Account (Blob containers + Azure Files share), and (auto-created) a Container Registry. Secrets live as Container App secrets. Entra External ID is provisioned at the **tenant** level, outside this resource group.

**Removed from the original plan (not available / not needed):** standalone Azure Cache for Redis, standalone Key Vault, manually-provisioned ACR. None are on the critical path.

---

## 2. Effort summary — where the work actually is

| Area | Difficulty | Why |
|---|---|---|
| Redis → Azure Cache | **Trivial** | Connection-string swap only. |
| Backend hosting → Container Apps | **Easy** | Already has a Dockerfile; remove Railway files, add IaC. |
| Postgres data → Azure Postgres | **Easy–Medium** | `pg_dump`/restore; 38 SQL migrations already exist. |
| `.table()` query layer (69 files) | **Medium** | Funnels through `db/supabase_client.py` — fix the seam, not 69 files (§4.1). |
| Storage → Blob (4 buckets) | **Medium** | Funnels through `core/storage.py` + 2 others (§4.3). |
| Frontend → Container Apps | **Medium** | Standalone build + drop `runtime='edge'` in ~12 routes (§5). |
| **Auth → Entra External ID** | **Hard** | New token model (RS256/JWKS), MSAL on frontend, **user re-keying** (§4.2, §6.3). This is the critical-path risk. |

---

## 3. Environment variable mapping

| Today (Supabase/Railway/Vercel) | Azure replacement |
|---|---|
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY` | **Removed** (no Supabase client) |
| `SUPABASE_JWT_SECRET` | **Removed** → `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_AUTHORITY`, `ENTRA_JWKS_URI`, `ENTRA_AUDIENCE` |
| `SUPABASE_DB_URL` | `DATABASE_URL` → Azure Postgres connection string (sslmode=require) |
| `REDIS_URL` | **Leave empty / remove** — `core/cache.py` falls back to in-process LRU automatically |
| `STORAGE_ROOT=/data` | Unchanged path; backed by mounted **Azure Files** share |
| *(new)* | `AZURE_STORAGE_ACCOUNT` + **Managed Identity** for Blob (preferred), or `AZURE_STORAGE_CONNECTION_STRING` |
| `FRONTEND_URL` | New Azure frontend URL (Container App FQDN / custom domain) |
| `ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `VERCEL_GATEWAY_API_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `NEWSAPI_KEY` | Unchanged values → **Container App secrets** (Key Vault optional later) |
| Frontend `NEXT_PUBLIC_API_URL` | Point at new backend Container App URL |
| *(new frontend)* | `NEXT_PUBLIC_ENTRA_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_AUTHORITY`, `NEXT_PUBLIC_ENTRA_REDIRECT_URI`, `NEXT_PUBLIC_ENTRA_API_SCOPE` |

---

## 4. Backend file changes (`DevBackend`)

### 4.1 Database / PostgREST layer — the big lever

915 `.table(...)` / client calls live across 69 files but they all obtain the client from **`db/supabase_client.py`**. Do **not** rewrite 69 files. Two viable strategies:

- **Option A — Self-host PostgREST (recommended for lowest code churn).** Run the open-source `postgrest` image as a second container against Azure Postgres. Keep `postgrest-py` (already a transitive dep) and rewrite only `db/supabase_client.py` so `get_supabase()` returns a thin object exposing `.table()` backed by `postgrest-py` pointed at the self-hosted endpoint. ~1 file changed; query semantics preserved.
- **Option B — In-process asyncpg shim.** Replace `get_supabase()` with a small query-builder shim that translates `.select().eq().order().execute()` into asyncpg SQL. More code in one place, no extra container, no PostgREST runtime. Higher initial effort, lower operational footprint.

**Files to change for the DB layer:**
- `db/supabase_client.py` — **rewrite.** `get_supabase()` / `get_supabase_with_token()` return the new client (PostgREST sidecar or shim). `get_auth_client()` is auth-only — see §4.2.
- `db/async_db.py` — **config only.** Already pure asyncpg; just reads the new `DATABASE_URL`. Verify SSL (`ssl=require`) for Azure Postgres.
- `config.py` — replace `supabase_db_url` with `database_url`; drop `supabase_*` keys (§4.4).
- `db/migrations/*.sql` — **review.** 38 files. Remove/replace anything referencing the Supabase `auth.users` schema, `auth.uid()` RLS, or Supabase-managed roles. RLS is moot once the backend uses a service connection — drop or neutralize RLS policies.
- `db/__init__.py`, `main.py` (pool init) — verify imports still resolve.

### 4.2 Auth — Supabase Auth → Entra External ID

> **Permission gate:** Entra External ID requires creating a CIAM tenant (directory-level). If you lack rights to create one in tenant `b6a9681f-…`, fall back to **self-hosted JWT** (bcrypt + own HS256 issuance in `auth.py`); in that case `dependencies.py` keeps local verification but signs with your own `SECRET_KEY`, and no user re-keying to external object ids is needed (only password re-hashing). Decide this before starting §6.3.

- `api/dependencies.py` — **rewrite token verification.** `_verify_jwt_local` moves HS256+`SUPABASE_JWT_SECRET` → **RS256 via Entra JWKS** (fetch + cache signing keys from `ENTRA_JWKS_URI`, validate `iss`/`aud`/`exp`). Delete `_verify_jwt_supabase` (the `get_auth_client().auth.get_user()` fallback). User id becomes the Entra `oid`/`sub` claim.
- `api/routes/auth.py` — **gut and reduce.** Register / login / password-reset / token-refresh move to Entra hosted flows. Keep only profile endpoints (`GET/PUT /auth/me`) that upsert a `user_profiles` row keyed by Entra `oid`. Remove all `supabase.auth.*` calls.
- `db/supabase_client.py::get_auth_client` — **delete** (no Supabase auth).
- User-profile bootstrap (in `api/dependencies.py` ~lines 174–251) — re-key from Supabase UUID to Entra object id; auto-create on first authenticated call.
- SMTP settings in `config.py` — keep only if used for non-reset email; otherwise remove.

### 4.3 Storage — Supabase Storage → Azure Blob

Funnels through three files via `.storage.from_(bucket)`:
- `core/storage.py` — **rewrite** `StorageHelper` to use `azure-storage-blob` (`upload_blob`, `download_blob`, `delete_blob`). Keep the public method signatures, magic-byte validation, and size limits so callers don't change. Map buckets → containers: `user-uploads`, `presentations`, `brain-docs`, `skills-bundles`.
- `core/file_store.py` — **edit** the 3-tier store: tier 3 (Supabase Storage fallback) → Blob; tier 2 (Railway volume) stays but is backed by the Azure Files mount.
- `core/skills/skill_storage.py` — **edit** skill-bundle archive read/write to Blob.
- `api/routes/upload.py`, `api/routes/skills_upload.py` — **verify** (should be unchanged if they call `StorageHelper`).
- Add `azure-storage-blob` to `requirements.txt`; remove `supabase`/`storage3` if fully unused.

### 4.4 Config

- `config.py` — drop `supabase_url/key/service_key/jwt_secret/db_url`; add `database_url`, `entra_*`, `azure_storage_*`. Update `frontend_url` default off the Vercel URL. `secret_key`/`algorithm`/`access_token_expire_minutes` no longer used for verification (Entra owns tokens) — remove or repurpose.

### 4.5 CORS & hardcoded URLs

- `main.py:328` — `allow_origins=["*"]` → explicit allow-list with the new frontend FQDN; if cookies/MSAL need it set `allow_credentials=True` (cannot combine with `*`).
- `config.py:70` — `frontend_url` default `https://potomacdeveloper.vercel.app` → Azure URL.
- `core/llm/openrouter_provider.py` — `FRONTEND_URL` referer default `https://potomac.ai` → confirm/keep.

### 4.6 Deploy / runtime files

- **Delete:** `railway.json`, `nixpacks.toml`, `Procfile` (Railway-only).
- `Dockerfile` — keep (multi-stage works on Container Apps). Confirm port: Dockerfile uses **8000**, `railway.json`/`main.py` default differs (8080) — standardize on one and set Container App ingress to match. Heavy system deps (libreoffice, tesseract, ffmpeg) are fine on Container Apps but increase image size/cold start → keep min-replicas ≥ 1.
- `docker-compose.yml` / `start.sh` — keep for **local dev only** (Postgres + Redis + API); they don't deploy to Azure.
- **Add:** `infra/` IaC (Bicep or `azd`) for ACR, Container Apps env + 2 apps, Postgres, Storage (Blob + Files), Redis, Key Vault.
- **Add:** `.github/workflows/backend.yml` — build → push ACR → `az containerapp update`.

### 4.7 Background work — Container Apps caveat

- `core/yang_autopilot.py` (polls `scheduled_jobs` every 30s) and `core/task_manager.py` (in-memory) require an **always-warm single instance**. Set Container App **min-replicas = 1** and either cap **max-replicas = 1** or make the scheduler leader-elect — otherwise multiple replicas double-fire scheduled goals. The in-memory task manager already loses state on restart (pre-existing limitation; unchanged by migration).
- `api/routes/websocket_router.py` — Container Apps supports WebSockets; ensure ingress allows them and sticky routing if scaled out.

---

## 5. Frontend file changes (`AnalystDevelopmentFrontEnd`)

### 5.1 Hosting (edge → Node standalone)
- `next.config.js` — add `output: 'standalone'`; `rewrites()` backend URL default off Railway → Azure backend.
- Remove `export const runtime = 'edge'` (→ default `nodejs`) in the ~12 edge routes: `app/api/chat/route.ts`, `chat/tool-result`, `health`, `skills/*`, `yang/goal/*`, `yang/memory`, `yang/schedule`. Streaming still works under Node.
- **Delete:** `vercel.json`, `.vercelignore`.
- **Add:** frontend `Dockerfile` (Next standalone) + `.github/workflows/frontend.yml`.
- `.env.example` / deployment env — `NEXT_PUBLIC_API_URL` → Azure backend; add Entra `NEXT_PUBLIC_*` vars.
- `src/lib/env.ts` — update default API URL + validation.

### 5.2 Auth (Entra / MSAL) — biggest frontend change
- Add `@azure/msal-browser` + `@azure/msal-react`.
- `src/contexts/AuthContext.tsx` — replace localStorage-JWT + `/api/auth/me` bootstrap with MSAL (`loginRedirect`, `acquireTokenSilent`).
- `src/lib/api.ts` — token injection: pull access token from MSAL instead of `localStorage.auth_token`; drop the custom `/auth/refresh` 401 logic (MSAL handles refresh).
- `app/login/page.tsx`, `app/register/page.tsx`, `app/forgot-password/page.tsx` — redirect into Entra hosted flows.
- **Delete/neuter:** `app/api/auth/login`, `app/api/auth/register`, `app/api/auth/me` proxy routes (Entra issues tokens directly; `me` may stay as a thin profile proxy to the backend).
- `src/components/ProtectedRoute.tsx` — gate on MSAL account instead of context user.
- `src/lib/uploadConversationFile.ts` — read token from MSAL, not `localStorage`.

---

## 6. Data migration

1. **Postgres:** `pg_dump` Supabase (schema + data) → restore into Azure Postgres Flexible Server. Drop Supabase-specific `auth.*` schema and RLS. Validate row counts.
2. **Storage:** copy all objects from the 4 Supabase buckets → matching Blob containers (`azcopy` from signed URLs, or a one-off script using both SDKs). Path convention `{file_id}/{filename}` is preserved.
3. **Users (hardest):** existing accounts live in Supabase Auth keyed by UUID; `user_profiles.id` references that UUID. Entra issues **new** object ids. Plan a migration: bulk-create users in Entra (MS Graph), then **re-key** `user_profiles` (and any FK references) from old Supabase UUID → new Entra `oid`, or add an `entra_oid` column and map on first login. Users will need to reset passwords via Entra. **This is the migration's critical path — validate on a staging tenant first.**

---

## 7. Recommended cutover order (low-risk → high-risk)

1. **Infra up:** Resource Group, ACR, Postgres, Redis, Storage, Key Vault, Container Apps env (IaC).
2. **Data plane:** restore Postgres dump; copy storage objects.
3. **Backend seams (no behavior change):** swap Redis URL; swap DB layer (§4.1); swap Storage layer (§4.3); deploy backend container to Container Apps, smoke-test against migrated data with auth still stubbed.
4. **Auth:** stand up Entra External ID tenant; implement RS256/JWKS verification (§4.2) and MSAL frontend (§5.2); migrate/re-key users (§6.3) on staging.
5. **Frontend:** standalone build, drop edge runtime, point at Azure backend, deploy to Container Apps.
6. **Cutover:** point DNS/custom domains at Azure; lock CORS to the new origin; decommission Vercel + Railway + Supabase after a soak period.

---

## 8. Top risks / watch-items
- **User re-keying to Entra** (§6.3) — forces password resets and FK remapping; highest-effort, do first on staging.
- **`.table()` semantics** — if going with the in-process shim (Option B), edge cases (upsert, range, `.or_()`, joins) must be covered or some of the 69 files break at runtime. The PostgREST sidecar (Option A) avoids this.
- **Scheduler double-firing** — pin min=max=1 replica or add leader election (§4.7).
- **Port mismatch** 8000 vs 8080 across Dockerfile/main.py/railway.json — standardize before deploy.
- **CORS + credentials** — `*` origins can't be combined with `allow_credentials=True`; MSAL may require the explicit origin.
- **Image cold start** — heavy OCR/office deps; keep a warm replica.
