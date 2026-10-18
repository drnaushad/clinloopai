# Cybersecurity and data protection summary

**Status: draft for the hospital's information security officer and privacy officer.** Version 0.1,
October 2026. No penetration test has been done yet (§6).

## 1. Architecture and trust boundaries

```
 Hospital FHIR server ──(read-only, SMART Backend Services or token)──▶ ClinLoop server ◀── staff browsers
 Hospital identity provider ──(OpenID Connect, PKCE)──────────────────▶   (one container,     (worklist, EHR cards)
                                                                          SQLite database)
```

- One container (`Dockerfile`: `python:3.12-slim`, runs as the unprivileged user `clinloop`, health
  check) and one database file. Everything runs inside the hospital network.
- In the core profile ClinLoop makes **no outbound connection with patient data**. It reads from the
  hospital's FHIR server and identity provider only. The optional literature lookups send rule-level
  search terms (for example "Fleischner pulmonary nodule guideline"), never patient data; the
  hospital can block them at the firewall. BioMCP, the largest of them, is off in the core profile
  unless the hospital sets `CLINLOOP_BIOMCP=1`; when off it is never started or contacted.
- ClinLoop writes nothing to the EHR. EHR integration is read-only cards (CDS Hooks).

## 2. Controls in place

| Area | Control | Where |
| --- | --- | --- |
| Staff authentication | Hospital single sign-on (OpenID Connect with PKCE, signature and audience checked); roles from the person's groups; a valid sign-in without a ClinLoop role is refused | `oidc.py`, `js/appnav.js` |
| Service accounts | Issued bearer tokens compared in constant time; roles viewer, navigator, clinician, admin | `auth.py` |
| Authorisation | Every patient-data endpoint requires a role; administration needs admin; the silent run further limits loops to the named review team | `require_role`, `pilot.py` |
| FHIR connection | SMART Backend Services: signed client assertion (RS384 or ES384), read-only scopes for each resource type it reads, token renewal; private key stays on the server; public key at `/.well-known/jwks.json` | `smart_auth.py` |
| Record of access | Hash-chained access log of every read of identifiable data (who, when, client address, which patients); data not shown if the record cannot be written | `access_recorder`, `loop_store.py` |
| Record of actions | Hash-chained audit log; `GET /api/v1/audit/verify` | `loop_store.py` |
| Browser | CORS limited to configured origins (`CLINLOOP_CORS_ORIGINS`), never a wildcard | `api.py` |
| Errors and logs | Logs carry types and counts, never names, identifiers, report text or values; error responses are generic (AGENTS.md §5) | throughout |
| Data minimisation | Exports for analysis are de-identified (hashed ids, no free text); text is de-identified before any model in the research profile | `pilot.export_csv`, `scrub_identifiers` |
| Scope | Core profile locks off model and image features, so fewer components handle patient data | `profile.py` |
| Supply chain | All dependencies pinned (`requirements.lock`); SBOM in CycloneDX (`sbom.cdx.json`), checked against the lock file by the tests | `scripts/build_sbom.py` |
| Build | Image built by CI from the repository, published to GHCR; tests must pass first | `.github/workflows/docker-publish.yml` |

## 3. What the hospital must provide

These are not in the container and are required for clinical use:

| Need | Why |
| --- | --- |
| TLS (HTTPS) in front of ClinLoop, e.g. the hospital's reverse proxy or load balancer | The container serves plain HTTP. Tokens and patient data must not cross the network unencrypted; single sign-on also needs a secure context |
| Encryption at rest of the volume holding the database | SQLite is not encrypted by ClinLoop |
| Backups of the database volume, tested restores | Audit, access and loop history live there (risk H-12) |
| Network rules: inbound only from staff networks and the EHR; outbound only to the FHIR server and identity provider | Limits exposure and data leaving the hospital |
| Secrets (`CLINLOOP_API_TOKENS`, SMART private key) in the hospital's secret store, rotated | Tokens are long-lived until rotated |
| Account life cycle in the identity provider (leavers removed) | Roles come from groups |

## 4. Threats considered

| Threat | Main controls | Residual concern |
| --- | --- | --- |
| Stolen or guessed token | Long random tokens, SSO for people, access log, constant-time comparison | No rate limiting in the application: put it on the reverse proxy |
| A staff member browsing patients without need | Access log with patient list per view; access-log review (post-market plan §2) | Review is a manual process |
| Tampering with the audit trail by someone with database access | Hash chain detects changes on verification | An attacker with full write access can rebuild the chain; keep off-server copies of the chain head |
| Malicious FHIR content (oversized, malformed) | Size limits on uploads, validation of request bodies, parsing without code execution | Fuzzing not yet done |
| Prompt injection into a model | Models off in the core profile; in research, the agent guard and fixed output formats | n/a in core |
| Vulnerable dependency | Pinned lock file, SBOM for scanning | Scanning schedule is the hospital's (§5) |
| Cross-site requests | CORS allow-list; bearer tokens, not cookies | — |

## 5. Vulnerability handling

1. The hospital scans `sbom.cdx.json` (or the GHCR image) with its usual scanner, at least monthly
   and on each release.
2. A vulnerability affecting ClinLoop is fixed by raising the range in `requirements*.txt`,
   regenerating `requirements.lock` and the SBOM (`python scripts/build_sbom.py`), and running the full
   test suite (AGENTS.md §5).
3. Critical issues: fixed release within 14 days, or a documented mitigation sooner.
4. Report security problems privately to the maintainers, not in a public issue.

## 6. Not yet done

- Independent penetration test and threat-model review.
- Fuzzing of the FHIR and upload parsers.
- Korean information security certification questions (e.g. ISMS-P scope) for the hospital's
  deployment: to be answered with the hospital's security team.
- PIPA privacy impact assessment, if the hospital's processing requires one.
