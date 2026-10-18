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
| **Epic sandbox** | Backend Services with ClinLoop's public key | See the limitation below |

**Epic and population-level reading.** The sync finds changed patients with searches across all
patients (`_lastUpdated`). Epic's FHIR R4 searches generally need a patient, and Epic provides
population data through Bulk FHIR (`$export`) instead. Expect the check to show those searches as
not supported. Bulk FHIR export is not built yet (see `docs/PRODUCTION_READINESS.md` §5).

## 4. Settings summary

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
| `CLINLOOP_FHIR_SYNC_MINUTES` / `CLINLOOP_FHIR_INITIAL_DAYS` | Sync interval and first look-back |

If login fails at start-up (for example, an unreadable key), the background sync does not start and
the data-feed banner on the worklist turns red, so the gap is visible.
