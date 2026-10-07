"""Load documents into the knowledge base.

    python -m airaa.kb.ingest --default                    # api-docs/*.json (OpenAPI) shipped with the repo
    python -m airaa.kb.ingest docs/aave.md notes/*.txt     # local .md / .txt / .json (OpenAPI) files
    python -m airaa.kb.ingest https://docs.aave.com/...    # web pages (HTML reduced to text)
    python -m airaa.kb.ingest --source aave-docs <paths>   # label where the documents came from

Re-running is cheap: a document whose text did not change is skipped without calling the embedding API.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import httpx

logger = logging.getLogger(__name__)
API_DOCS = Path(__file__).resolve().parents[2] / "api-docs"
Doc = Tuple[str, str, str]   # (url, title, text)


# ---------------------------------------------------------------- loaders
def openapi_documents(spec: Dict, source_url: str) -> List[Doc]:
    """One document per OpenAPI tag, one paragraph per endpoint (path, summary, parameters, response)."""
    title = spec.get("info", {}).get("title", "API")
    base = (spec.get("servers") or [{"url": ""}])[0].get("url", "")
    by_tag: Dict[str, List[str]] = {}
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch"} or not isinstance(op, dict):
                continue
            lines = [f"{method.upper()} {base}{path}", op.get("summary") or op.get("description") or ""]
            for param in op.get("parameters", []):
                if isinstance(param, dict) and param.get("name"):
                    required = "required" if param.get("required") else "optional"
                    lines.append(f"Parameter {param['name']} ({param.get('in', 'query')}, {required}): {param.get('description', '')}".strip())
            ok = (op.get("responses") or {}).get("200") or {}
            if ok.get("description"):
                lines.append(f"Returns: {ok['description']}")
            for tag in op.get("tags") or ["General"]:
                by_tag.setdefault(tag, []).append("\n".join(line for line in lines if line))
    return [(f"{source_url}#{re.sub(r'[^a-z0-9]+', '-', tag.lower()).strip('-')}", f"{title}: {tag}", "\n\n".join(entries))
            for tag, entries in by_tag.items()]


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "pre"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr", "pre"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data)


def html_to_text(html: str) -> Tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    return parser.title.strip(), re.sub(r"\n\s*\n+", "\n\n", text).strip()


def load_path(path: Path) -> List[Doc]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        spec = json.loads(raw)
        if isinstance(spec, dict) and "paths" in spec:
            site = {"DefiLlama API": "https://api-docs.defillama.com/"}.get(spec.get("info", {}).get("title", ""), path.resolve().as_uri())
            return openapi_documents(spec, site)
        return [(path.resolve().as_uri(), path.stem, json.dumps(spec, indent=1))]
    return [(path.resolve().as_uri(), path.stem.replace("-", " ").replace("_", " ").title(), raw)]


def load_url(url: str) -> List[Doc]:
    response = httpx.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "airaa-kb-ingest/1.0"})
    response.raise_for_status()
    if "html" in response.headers.get("content-type", ""):
        title, text = html_to_text(response.text)
        return [(url, title or url, text)]
    return [(url, url.rsplit("/", 1)[-1] or url, response.text)]


def collect(targets: Iterable[str], default: bool) -> List[Doc]:
    docs: List[Doc] = []
    if default:
        for path in sorted(API_DOCS.glob("*.json")):
            docs.extend(load_path(path))
    for target in targets:
        if re.match(r"^https?://", target):
            docs.extend(load_url(target))
        else:
            docs.extend(load_path(Path(target)))
    return docs


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="files or URLs")
    parser.add_argument("--default", action="store_true", help="ingest the repo's api-docs/")
    parser.add_argument("--source", default="docs", help="label stored with each document")
    args = parser.parse_args(argv)
    logging.basicConfig(level="INFO", format="%(message)s")

    from ..config import get_settings
    from ..db import get_pool
    from ..db.kb_repo import KbRepo
    from ..embeddings import Embedder
    from .service import KnowledgeBase

    settings = get_settings()
    pool = get_pool()
    if pool is None:
        print("DATABASE_URL is not set (or the database is unreachable)", file=sys.stderr)
        return 1
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is required to create embeddings", file=sys.stderr)
        return 1
    if not args.targets and not args.default:
        parser.print_usage()
        return 2

    kb = KnowledgeBase(KbRepo(pool), Embedder(settings), settings)
    tally: Dict[str, int] = {}
    for url, title, text in collect(args.targets, args.default):
        status = kb.ingest_document(args.source, url, title, text)
        tally[status] = tally.get(status, 0) + 1
        print(f"{status:9} {title}")
    print("Done: " + ", ".join(f"{n} {k}" for k, n in sorted(tally.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
