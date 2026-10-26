# Connecting ClinLoop to a FHIR R4 server

ClinLoop reads a hospital FHIR R4 server on a schedule (`fhir_sync.py`). It only reads; it never
writes to the record. This page covers logging in, checking the connection, and the sandboxes to
try first. Use a sandbox with synthetic patients until the hospital's approvals are in place.

## 1. Logging in

| Method | When | Settings |
| --- | --- | --- |
| **SMART Backend Services** (signed key) | Hospital servers (Epic, Oracle Health, most FHIR gateways) and any server that supports it | `CLINLOOP_FHIR_CLIENT_ID`, `CLINLOOP_FHIR_PRIVATE_KEY` (and `CLINLOOP_FHIR_KEY_ID` if the server assigned one) |
| Client secret | Sandboxes without key login | `CLINLOOP_FHIR_CLIENT_ID`, `CLINLOOP_FHIR_CLIENT_SECRET`, `CLINLOOP_FHIR_SECRET_METHOD=basic\|post` |
| Static bearer token | Test servers only | `CLINLOOP_FHIR_TOKEN` |

With SMART Backend Services, ClinLoop signs a short-lived JWT with its private key (RS384 for RSA,
ES384 for EC P-384) and exchanges it for an access token. It finds the token endpoint in the
server's `.well-known/smart-configuration` (or the CapabilityStatement); set
`CLINLOOP_FHIR_TOKEN_URL` if the server publishes neither. Tokens are renewed shortly before they
expire, and once more if the server rejects one early.

ClinLoop asks only for read scopes on the resource types it reads: `system/<Type>.rs` (SMART v2) or
`system/<Type>.read` (v1), chosen from what the server advertises. Override with
`CLINLOOP_FHIR_SCOPE` if the hospital registered different scopes.

### Creating ClinLoop's key

```bash
python -m src.clinloop_engine.smart_auth --new-key /etc/clinloop/fhir      # RSA 3072 (RS384)
python -m src.clinloop_engine.smart_auth --new-key /etc/clinloop/fhir --ec # EC P-384 (ES384)
```

With docker compose, create it inside the container so it lands on the data volume, owned by the
unprivileged `clinloop` user:

```bash
docker compose exec clinloop-api python -m src.clinloop_engine.smart_auth --new-key /var/lib/clinloop/fhir
# then in .env: CLINLOOP_FHIR_PRIVATE_KEY=/var/lib/clinloop/fhir/clinloop_fhir_private.pem
```

This writes `clinloop_fhir_private.pem` (readable by its owner only; it is never overwritten) and
prints the public key set (JWKS). Give the FHIR server the public key set, either by uploading it or
by pointing it at `https://<clinloop server>/.well-known/jwks.json`, which ClinLoop serves when
`CLINLOOP_FHIR_PRIVATE_KEY` is set. The private key stays on the ClinLoop server. Keep it out of
the repository and out of backups that leave the hospital.

## 2. Checking the connection

```bash
python -m src.clinloop_engine.fhir_sync --check
```

or `GET /api/v1/fhir/check` with an admin token. The check reads the CapabilityStatement, logs in,
and then runs the sync's own search (`_lastUpdated=gt…`, one result) on each resource type. It
reports:
- the FHIR version (ClinLoop reads R4, 4.0.x);
- how it logged in and the scopes it requested;
- for each resource type, readable or not, with the reason: not logged in, not allowed (scopes), or
  search not supported.

The report contains HTTP outcomes only, never resource content or patient data. The command exits
with status 1 when a required type cannot be read.

## 3. Sandboxes

| Server | Login | Notes |
| --- | --- | --- |
| **Medplum** (hosted or self-hosted) | Client secret from a `ClientApplication` (`CLINLOOP_FHIR_SECRET_METHOD` as the server expects), or key login if the application is given ClinLoop's JWKS | FHIR base `https://api.medplum.com/fhir/R4` for the hosted service. Load synthetic patients (Synthea or `data/fhir_example_bundle.json`) into a project used for nothing else |
| **SMART Health IT launcher** | Backend Services, registering ClinLoop's JWKS | Synthetic patients only |
| **HAPI FHIR** (self-hosted test server) | Often none, or a static token | Good for loading `data/*.json` bundles and testing the sync end to end |
| **Epic sandbox** | Backend Services with ClinLoop's public key | Use Bulk FHIR mode (below) |

**Bulk FHIR mode (Epic and similar).** The default sync finds changed patients with searches across
all patients (`_lastUpdated`). Epic's FHIR R4 searches generally need a patient, and Epic provides
population data through Bulk FHIR (`$export`) instead. Set:

```
CLINLOOP_FHIR_MODE=bulk
CLINLOOP_FHIR_GROUP_ID=<the Group of patients ClinLoop may monitor>
```

Each sync then starts a Group-level export, waits for it (honouring `Retry-After`), downloads the
NDJSON files and deletes the job. The first run exports everything for the Group, so each
patient's history is complete; later runs export only what changed since the last export's
`transactionTime`. ClinLoop keeps the exported records in its own database (a local copy, read
when it evaluates a patient), so protect and back up that database as patient data. Without a
Group id, a system-level export (`<base>/$export`) is requested. An export not ready within
`CLINLOOP_FHIR_BULK_TIMEOUT_MINUTES` (default 60) is cancelled and the run is recorded as failed.
In this mode, `--check` reports whether the server declares `$export` and whether login works; it
does not start an export.

**Files on disk (Synthea, a saved export).** Before any server is available, a folder of FHIR files
can be run through the same sync:

```
python -m src.clinloop_engine.fhir_folder <folder> [--db run.db] [--evaluation-time 2026-09-01T00:00:00]
```

It reads Synthea's default output (one transaction Bundle per patient, `urn:uuid` references resolved
through each entry's `fullUrl`) and NDJSON (`exporter.fhir.bulk_data = true`, or Bulk FHIR files),
streaming one file or line at a time into the local copy, then evaluates every patient. The summary
holds counts only: files, resources by type, patients, loops per rule, unreadable lines and
references it had to assume. Use it to test mapping and scale; a synthetic run says nothing about
accuracy on real patients.

## 4. Separate browser EHR launch preview (synthetic SMART sandbox only)

`/smart/launch.html` provides a browser public-client demonstration, separate from the
Backend Services sync described above. Open its configured launcher link, use Provider
EHR Launch with FHIR R4, then launch ClinLoop and confirm synthetic sandbox data.

The registration is public client `clinloop-smart-sandbox-ui`, launch URL
`https://clinloopai.app/smart/launch.html`, redirect URL
`https://clinloopai.app/smart/callback.html`, with only
`launch patient/Patient.r patient/DiagnosticReport.rs`. The generated launcher enables
Strict validation and Always PKCE. Loopback previews use their own exact origin for both
URLs; do not register a preview redirect for a hospital client.

The preview requires S256 PKCE, unpredictable single-use state, a five-minute login
handshake and allowlisted SMART sandbox endpoints. It verifies the returned Patient
resource against launch context, reads up to 20 DiagnosticReport resources for that
patient, rejects mismatched subjects, and explicitly labels empty/partial data. It
does not follow pagination links, load attachments, execute FHIR XHTML or make clinical
decisions. Plain-text conclusions are displayed only when the source supplies them.

Only the temporary handshake is kept in sessionStorage. Access tokens and records are
not persisted or sent to ClinLoop's shared API or a model. Disconnect, page exit and ten
minutes of inactivity clear the view. Clearing is not server-side grant revocation or
secure memory deletion. This page does not implement hospital access auditing and is
not an approved workflow for real patient records. SMART sandbox interoperability does
not establish clinical accuracy, production OAuth certification or Epic clinician-launch
support; the existing Epic application remains a separate Backend Systems registration.

Run the browser security tests with `node tests/test_smart_sandbox.cjs`. Live verification
must include the actual launcher authorization/callback round trip; a mock token or the
SMART sample app is not evidence that ClinLoop's own flow works.

### HAPI browser test connection

The same `/smart/launch.html` page offers **Connect HAPI FHIR** without a login.
Confirm the synthetic cohort first. The browser reads metadata and two bounded tagged
searches directly from `https://hapi.fhir.org/baseR4`: Patients and DiagnosticReports.
Only the fixed ClinLoop test cohort and its known resource IDs are accepted. This is
not a general public-patient browser. No uploads, writes, pagination, attachments,
model calls or shared ClinLoop API calls are performed. The SMART callback keeps its
original SMART-only connection policy; HAPI never receives SMART tokens.

Source conclusions are plain text in page memory. Disconnect, page exit, restored
browser-cache pages and ten idle minutes clear the view. Public records can be reset
or edited: missing data, partial data or a successful connection never establishes
normal findings, completed follow-up or clinical accuracy. No source record is
imported into the clinical database. Backend ingestion remains a separate workflow.

Run `node tests/test_hapi_sandbox.cjs` for the HAPI boundary and lifecycle tests.
Live verification should record only connection status, resource counts and clearing
behavior. This preview is for synthetic interoperability checks only.

## 5. Settings summary

| Variable | Purpose |
| --- | --- |
| `CLINLOOP_FHIR_BASE` | FHIR R4 base URL |
| `CLINLOOP_FHIR_CLIENT_ID` | Client id issued by the server (turns on SMART login) |
| `CLINLOOP_FHIR_PRIVATE_KEY` | Path to ClinLoop's private key (PEM) |
| `CLINLOOP_FHIR_KEY_ID` | Key id registered with the server (default: the key's RFC 7638 thumbprint) |
| `CLINLOOP_FHIR_CLIENT_SECRET` / `CLINLOOP_FHIR_SECRET_METHOD` | Sandbox login without a key |
| `CLINLOOP_FHIR_TOKEN_URL` | Token endpoint, if the server does not publish one |
| `CLINLOOP_FHIR_SCOPE` | Scopes to request instead of the read-only default |
| `CLINLOOP_FHIR_TOKEN` | Static bearer token (test servers) |
| `CLINLOOP_FHIR_MODE` / `CLINLOOP_FHIR_GROUP_ID` | `search` (default) or `bulk` (Bulk FHIR export), and the Group to export |
| `CLINLOOP_FHIR_BULK_TIMEOUT_MINUTES` | How long to wait for an export (default 60) |
| `CLINLOOP_FHIR_SYNC_MINUTES` / `CLINLOOP_FHIR_INITIAL_DAYS` | Sync interval and first look-back |

If login fails at start-up (for example, an unreadable key), the background sync does not start and
the data-feed banner on the worklist turns red, so the gap is visible.
