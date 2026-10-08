"""
biomcp_client.py — Connection to the BioMCP server over the Model Context Protocol

BioMCP (open-source, `pip install biomcp-python`) is an MCP server that gives
access to biomedical sources: PubMed/PubTator3 articles, ClinicalTrials.gov,
openFDA drug labels and adverse events, MyGene/MyVariant/MyChem and more.
ClinLoop connects to it as an MCP client:

  * CLINLOOP_BIOMCP_URL set   → streamable HTTP, e.g. http://biomcp:8000/mcp
                                 (server started with `biomcp run --mode streamable_http`)
  * otherwise                 → stdio: ClinLoop launches `biomcp run` itself
                                 (CLINLOOP_BIOMCP_COMMAND overrides the command)

Only read-only tools on an allowlist can be called. ClinLoop sends rule-level
search terms; it never puts patient data into a BioMCP query.

BioMCP returns an empty result (not an error) when its upstream sources are
unreachable, so callers must not read "no results" as "no evidence exists".
"""

import asyncio
import json
import os
import shlex
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .literature import EVIDENCE_QUERIES, _cache

STATUS_TTL = 5 * 60
CALL_TTL = 24 * 3600
CALL_TIMEOUT = 60.0

# Read-only BioMCP tools ClinLoop may call
ALLOWED_TOOLS = {
    "search", "fetch",
    "article_searcher", "article_getter",
    "trial_searcher", "trial_getter",
    "drug_getter", "disease_getter", "gene_getter",
    "variant_searcher", "variant_getter",
    "openfda_label_searcher", "openfda_label_getter",
    "openfda_adverse_searcher", "openfda_recall_searcher",
    "openfda_shortage_searcher", "openfda_approval_searcher",
}


class BioMCPError(RuntimeError):
    pass


def _transport() -> Dict[str, Any]:
    url = os.environ.get("CLINLOOP_BIOMCP_URL")
    if url:
        return {"kind": "streamable_http", "url": url}
    command = os.environ.get("CLINLOOP_BIOMCP_COMMAND", "biomcp run")
    argv = shlex.split(command)
    if not argv or not shutil.which(argv[0]):
        return {"kind": "unavailable", "reason": f"'{argv[0] if argv else command}' not installed "
                                                  "(pip install biomcp-python) and CLINLOOP_BIOMCP_URL not set"}
    return {"kind": "stdio", "argv": argv}


async def _with_session(fn):
    """Open an MCP session to BioMCP, run `fn(session)`, close it."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    t = _transport()
    if t["kind"] == "unavailable":
        raise BioMCPError(t["reason"])
    if t["kind"] == "streamable_http":
        async with streamablehttp_client(t["url"], timeout=CALL_TIMEOUT) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                return await fn(session, init)
    params = StdioServerParameters(command=t["argv"][0], args=t["argv"][1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            return await fn(session, init)


def _run(coro):
    try:
        return asyncio.run(asyncio.wait_for(coro, CALL_TIMEOUT))
    except BioMCPError:
        raise
    except Exception as e:  # transport errors, timeouts, protocol errors
        raise BioMCPError(f"{type(e).__name__}: {e}") from e


def status(force: bool = False) -> Dict:
    """Connect, initialize and list tools. Cached for 5 minutes."""
    if not force:
        cached = _cache.get("health|biomcp", STATUS_TTL)
        if cached is not None:
            return cached
    t = _transport()
    t0 = time.perf_counter()

    async def probe(session, init):
        tools = await session.list_tools()
        return init, [tool.name for tool in tools.tools]

    try:
        init, names = _run(_with_session(probe))
        result = {"status": "ok", "transport": t["kind"], "server": init.serverInfo.name,
                  "version": init.serverInfo.version, "tools": len(names),
                  "allowed_tools": sorted(set(names) & ALLOWED_TOOLS),
                  "latency_ms": round((time.perf_counter() - t0) * 1000)}
    except BioMCPError as e:
        result = {"status": "not_installed" if t["kind"] == "unavailable" else "unreachable",
                  "transport": t["kind"], "error": str(e)}
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    _cache.put("health|biomcp", result)
    return result


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict:
    """Call one allowlisted BioMCP tool; returns parsed JSON when the tool returns JSON."""
    if name not in ALLOWED_TOOLS:
        raise BioMCPError(f"Tool '{name}' is not on ClinLoop's read-only allowlist")
    key = f"biomcp|{name}|{json.dumps(arguments, sort_keys=True)}"
    cached = _cache.get(key, CALL_TTL)
    if cached is not None:
        return cached

    async def call(session, _init):
        return await session.call_tool(name, arguments)

    res = _run(_with_session(call))
    texts = [getattr(c, "text", "") for c in res.content]
    if res.isError:
        raise BioMCPError(" ".join(texts)[:500] or f"{name} failed")
    joined = "\n".join(texts)
    try:
        data: Any = json.loads(joined)
    except ValueError:
        data = joined
    result = {"tool": name, "arguments": arguments, "result": data,
              "retrieved_at": datetime.now(timezone.utc).isoformat()}
    if data in ([], "", None):
        result["note"] = ("No results. BioMCP returns an empty list when its upstream sources "
                          "(PubMed/PubTator3, Europe PMC, …) are unreachable, so this does not mean "
                          "that no evidence exists.")
    else:
        _cache.put(key, result)   # cache only real answers
    return result


def rule_articles(rule_id: str) -> Dict:
    """BioMCP article search for one rule (rule-level keywords only)."""
    query = EVIDENCE_QUERIES.get(rule_id)
    if query is None:
        raise KeyError(rule_id)
    return {"rule_id": rule_id, "source": "biomcp", "query": query,
            **call_tool("article_searcher", {"keywords": [query]})}
