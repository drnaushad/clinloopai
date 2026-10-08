"""
literature.py — Live literature connections (PubMed, Europe PMC) and service status

PubMed (NCBI E-utilities) and Europe PMC are free public APIs. ClinLoop
queries them with RULE-LEVEL search terms only (e.g. "Fleischner pulmonary
nodule guideline"); patient data is never sent to any external service.

Results are cached in memory (24 h for searches, 5 min for health checks) to
respect NCBI's rate limits (3 requests/s, or 10/s with NCBI_API_KEY).

Configuration (environment):
  NCBI_API_KEY              optional NCBI key (higher rate limit)
  CLINLOOP_PUBMED_BASE      default https://eutils.ncbi.nlm.nih.gov/entrez/eutils
  CLINLOOP_EUROPEPMC_BASE   default https://www.ebi.ac.uk/europepmc/webservices/rest
  CLINLOOP_LITERATURE       set to "off" to disable all outbound literature calls
"""

import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
TOOL_NAME = "clinloop-ai"
SEARCH_TTL = 24 * 3600
HEALTH_TTL = 5 * 60

# Rule-level evidence queries: guideline-focused, no patient information
EVIDENCE_QUERIES: Dict[str, str] = {
    "R001": "abnormal test results follow-up communication ambulatory patients",
    "R002": "abnormal laboratory results missed follow-up primary care",
    "R003": "Fleischner Society incidental pulmonary nodules guideline",
    "R004": "elevated PSA follow-up urology referral delay",
    "R005": "ASCCP risk-based management abnormal cervical cancer screening",
    "R006": "positive blood culture after emergency department discharge follow-up",
    "R007": "warfarin dose change INR monitoring interval",
    "R008": "specialist referral completion loop closure",
    "R009": "abnormal pathology result patient notification delay",
    "R010": "laboratory monitoring after medication initiation",
    "R011": "test result acknowledgment electronic health record",
    "R012": "levothyroxine dose adjustment TSH monitoring interval",
    "R013": "HbA1c testing frequency uncontrolled diabetes standards of care",
    "R014": "early outpatient follow-up after myocardial infarction discharge",
    "R015": "repeat blood cultures Staphylococcus aureus bacteremia clearance",
    "R016": "echocardiography new heart failure diagnosis guideline",
    "R017": "time to colonoscopy after positive fecal immunochemical test",
    "R018": "BI-RADS category 4 5 time to biopsy",
    "R019": "Lung-RADS category 4A follow-up adherence",
    "R020": "Lung-RADS 4B 4X diagnostic workup",
    "R021": "test results pending at hospital discharge",
    "R022": "critical laboratory value notification time",
    "R023": "heart failure hospitalization follow-up within 7 days readmission",
    "R024": "postpartum blood pressure monitoring hypertensive disorders of pregnancy",
    "R025": "postpartum glucose testing gestational diabetes",
    "R026": "hepatitis C antibody reflex RNA testing linkage to care",
    "R027": "hepatocellular carcinoma surveillance ultrasound chronic hepatitis B cirrhosis",
    "R028": "hepatocellular carcinoma surveillance interval six months adherence",
    "R029": "follow-up within 7 days after emergency department visit for self-harm",
    "R030": "radiologist follow-up imaging recommendations adherence",
    "R031": "radiologist recommended follow-up MRI completion",
    "R032": "radiologist recommended follow-up ultrasound completion",
    "R033": "follow-up chest radiograph pneumonia resolution lung cancer",
    "R034": "Lung-RADS category 3 adherence follow-up",
    "R035": "critical imaging findings communication radiology",
    "R036": "radiologist recommended biopsy completion follow-up",
    "R037": "incidental adrenal nodule follow-up imaging",
    "R038": "adrenal incidentaloma 4 cm management",
    "R039": "incidental solid renal mass urology referral",
    "R040": "Bosniak IIF cyst follow-up imaging",
    "R041": "incidental pancreatic cyst surveillance MRI",
    "R042": "pancreatic cyst worrisome features endoscopic ultrasound",
    "R043": "incidental thyroid nodule CT ultrasound evaluation",
    "R044": "incidental abdominal aortic aneurysm surveillance follow-up",
    "R045": "abdominal aortic aneurysm repair threshold referral",
    "R046": "growing pulmonary nodule management",
}


class LiteratureError(RuntimeError):
    pass


class _Cache:
    def __init__(self):
        self._data: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float):
        with self._lock:
            hit = self._data.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        return None

    def put(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_cache = _Cache()


def _enabled() -> bool:
    return os.environ.get("CLINLOOP_LITERATURE", "on").lower() != "off"


def _pubmed_base() -> str:
    return os.environ.get("CLINLOOP_PUBMED_BASE", PUBMED_BASE).rstrip("/")


def _europepmc_base() -> str:
    return os.environ.get("CLINLOOP_EUROPEPMC_BASE", EUROPEPMC_BASE).rstrip("/")


def _get(url: str, params: Dict, timeout: float = 10.0) -> Dict:
    if not _enabled():
        raise LiteratureError("Literature connections are disabled (CLINLOOP_LITERATURE=off)")
    try:
        resp = requests.get(url, params=params, timeout=timeout,
                            headers={"User-Agent": f"{TOOL_NAME}/1.0"})
    except requests.RequestException as e:
        raise LiteratureError(f"{type(e).__name__}: {e}") from e
    if resp.status_code != 200:
        raise LiteratureError(f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as e:
        raise LiteratureError("Invalid JSON response") from e


# ── PubMed (NCBI E-utilities) ────────────────────────────────────────────────

def search_pubmed(query: str, limit: int = 5) -> List[Dict]:
    """Most relevant PubMed articles for a query: pmid, title, journal, year, url."""
    key = f"pubmed|{query}|{limit}"
    cached = _cache.get(key, SEARCH_TTL)
    if cached is not None:
        return cached
    common = {"db": "pubmed", "retmode": "json", "tool": TOOL_NAME}
    if os.environ.get("NCBI_API_KEY"):
        common["api_key"] = os.environ["NCBI_API_KEY"]
    ids = _get(f"{_pubmed_base()}/esearch.fcgi",
               {**common, "term": query, "retmax": limit, "sort": "relevance"}
               ).get("esearchresult", {}).get("idlist", [])
    articles: List[Dict] = []
    if ids:
        summary = _get(f"{_pubmed_base()}/esummary.fcgi", {**common, "id": ",".join(ids)}).get("result", {})
        for pmid in ids:
            doc = summary.get(pmid, {})
            articles.append({
                "source": "PubMed",
                "pmid": pmid,
                "title": doc.get("title", "").rstrip("."),
                "journal": doc.get("fulljournalname") or doc.get("source", ""),
                "year": (doc.get("pubdate") or "")[:4],
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })
    _cache.put(key, articles)
    return articles


# ── Europe PMC ───────────────────────────────────────────────────────────────

def search_europepmc(query: str, limit: int = 5) -> List[Dict]:
    """Most relevant Europe PMC records for a query."""
    key = f"europepmc|{query}|{limit}"
    cached = _cache.get(key, SEARCH_TTL)
    if cached is not None:
        return cached
    data = _get(f"{_europepmc_base()}/search",
                {"query": query, "format": "json", "pageSize": limit, "resultType": "lite"})
    articles = []
    for r in data.get("resultList", {}).get("result", []):
        pmid = r.get("pmid")
        url = (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid
               else f"https://europepmc.org/article/{r.get('source', 'MED')}/{r.get('id', '')}")
        articles.append({
            "source": "Europe PMC",
            "pmid": pmid,
            "doi": r.get("doi"),
            "title": (r.get("title") or "").rstrip("."),
            "journal": r.get("journalTitle", ""),
            "year": str(r.get("pubYear", "")),
            "url": url,
        })
    _cache.put(key, articles)
    return articles


def evidence_for_rule(rule_id: str, source: str = "pubmed", limit: int = 5) -> Dict:
    query = EVIDENCE_QUERIES.get(rule_id)
    if query is None:
        raise KeyError(rule_id)
    fn = search_europepmc if source == "europepmc" else search_pubmed
    return {"rule_id": rule_id, "source": source, "query": query,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "articles": fn(query, limit)}


# ── Health checks ────────────────────────────────────────────────────────────

def _check(name: str, fn) -> Dict:
    cached = _cache.get(f"health|{name}", HEALTH_TTL)
    if cached is not None:
        return cached
    t0 = time.perf_counter()
    try:
        fn()
        result = {"status": "ok", "latency_ms": round((time.perf_counter() - t0) * 1000)}
    except LiteratureError as e:
        result = {"status": "disabled" if not _enabled() else "unreachable", "error": str(e)}
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    _cache.put(f"health|{name}", result)
    return result


def pubmed_status() -> Dict:
    return _check("pubmed", lambda: _get(f"{_pubmed_base()}/einfo.fcgi",
                                          {"db": "pubmed", "retmode": "json", "tool": TOOL_NAME}, timeout=5))


def europepmc_status() -> Dict:
    return _check("europepmc", lambda: _get(f"{_europepmc_base()}/search",
                                             {"query": "guideline", "format": "json", "pageSize": 1}, timeout=5))


def clear_cache() -> None:
    _cache.clear()
