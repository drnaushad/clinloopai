"""
Write js/engine_manifest.json: the engine files the "Analyse patient" page (analyse.html) downloads
into Pyodide to run the engine in the browser on the public website.

The list is every engine module ``src.clinloop_engine.browser_analyse`` can import, directly or
through the engine's lazy (in-function) imports, found by reading the source, plus the data files
those modules read while analysing a bundle. Modules reached only from the local-LLM note helper
(``note_reader.llm_suggestions``: network, OCR and image models) are left out: the browser never
calls it. Re-run after changing
engine imports; tests/test_analyse_page.py fails when the manifest is out of date.

    python scripts/build_engine_manifest.py
"""

import ast
import json
import os
from typing import Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(ROOT, "js", "engine_manifest.json")
ENTRY = "src.clinloop_engine.browser_analyse"
# Files read at run time (not imported): the hospital's critical-finding list (radiology.py)
DATA_FILES = ["src/clinloop_engine/config/critical_findings.json"]


# Network/model-inventory helpers reached only through backend model calls: never used in the browser
NOT_IN_BROWSER = {"document_reader", "local_llm_engine", "imaging_ai", "model_registry"}
PACKAGE = os.path.join(ROOT, "src", "clinloop_engine")


def engine_modules() -> List[str]:
    """Engine modules reachable from the entry point through relative imports, at any depth in the code."""
    seen, todo = set(), [ENTRY.rsplit(".", 1)[1]]
    while todo:
        name = todo.pop()
        if name in seen or name in NOT_IN_BROWSER:
            continue
        seen.add(name)
        with open(os.path.join(PACKAGE, name + ".py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                todo.append(node.module.split(".")[0])
    return sorted(seen)


def build() -> Dict:
    files = ["src/clinloop_engine/__init__.py"] + [f"src/clinloop_engine/{m}.py" for m in engine_modules()]
    # numpy from the Pyodide repository; networkx as its wheel file alone (by name, Pyodide would also
    # load matplotlib and other optional dependencies the engine never imports)
    return {"pyodide": "0.26.4", "packages": ["numpy", "networkx-3.3-py3-none-any.whl"], "entry": ENTRY,
            "files": sorted(files + DATA_FILES)}


def main() -> None:
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(build(), f, indent=1)
        f.write("\n")
    print(f"wrote {os.path.relpath(MANIFEST, ROOT)}")


if __name__ == "__main__":
    main()
