"""Canned upstream content and routing, shared across test modules."""

from __future__ import annotations

from fastapi_docs_mcp.config import DOCS_RAW_BASE, REPO_RAW_ROOT, SITEMAP_URL

FAKE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <loc>https://fastapi.tiangolo.com/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/first-steps/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/cors/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/security/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/sql-databases/</loc>
  <loc>https://fastapi.tiangolo.com/advanced/websockets/</loc>
  <loc>https://fastapi.tiangolo.com/some-random-page/</loc>
</urlset>"""

FAKE_CORS_MD = """# CORS (Cross-Origin Resource Sharing) { #cors }

Configure CORS with a [link](https://example.com) and an ![shot](https://x.png).

/// note | Technical Details

You could also import from starlette.

///

/// tip

Be explicit.

///

{* ../../docs_src/cors/tutorial001.py ln[1:3] *}

```console
$ fastapi dev
Started server
lots of logs here
```

```json
{"hello": "world"}
```
"""

FAKE_CORS_PY = """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
origins = ["http://localhost"]
"""

FAKE_SECURITY_MD = "# Security\n\nUse OAuth2 and JWT for auth.\n"


def route(url: str) -> str | None:
    """Serve canned content for the URLs the fake upstream "knows about".

    Anything else returns ``None`` — i.e. every unmapped URL behaves like a
    confirmed 404, not a transient failure (see ``http.UpstreamError``).
    """
    if url == SITEMAP_URL:
        return FAKE_SITEMAP
    if url == f"{DOCS_RAW_BASE}/tutorial/cors.md":
        return FAKE_CORS_MD
    if url == f"{REPO_RAW_ROOT}/docs_src/cors/tutorial001.py":
        return FAKE_CORS_PY
    if url == f"{DOCS_RAW_BASE}/tutorial/security.md":
        return FAKE_SECURITY_MD
    return None
