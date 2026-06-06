# Lessons

## Preserve dynamic discovery & upstream-resilience — don't optimize it away
**Context:** Proposed switching content fetch from live-site HTML scraping to GitHub markdown source for token
quality. The user valued that the original design was *dynamic*: sitemap-driven discovery, no hardcoded paths,
and resilient to the FastAPI maintainer adding/moving docs.

**Mistake:** The markdown pivot quietly coupled the server to GitHub **repo internals** (directory layout +
include syntax — which FastAPI has already changed once: `{!...!}` → `{* *}`). That trades away upstream
resilience even though sitemap *discovery* stayed dynamic. I over-weighted token quality vs. robustness.

**Rule for myself:**
- When optimizing how data is fetched, separate **discovery** (must stay dynamic — sitemap is the contract)
  from **acquisition** (may be optimized). Never let an optimization make the server break on legitimate
  upstream changes.
- Prefer **layered fallback** over hard cutover: markdown-preferred → HTML fallback keeps the "never breaks"
  guarantee while still capturing the token win.
- Treat the **public contract** (site URLs in the sitemap) as more stable than **implementation details**
  (a repo's internal file layout / templating syntax). Couple to the former, not the latter.
- Hardcoded config (e.g. `compare`'s topic→pages map) should be **self-healing**: validate against the live
  source at runtime and degrade dynamically, rather than emitting dead references.
