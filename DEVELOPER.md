# Developer & Technical Architecture Guide

This document provides complete technical documentation for developers, software maintainers, and researchers modifying or extending the **Adaptive News Article and Comment Collector**.

---

## Table of Contents

1. [Architecture & Component Design](#architecture--component-design)
2. [Data Models & Schema Contracts](#data-models--schema-contracts)
3. [Source Routing & Adapter Isolation](#source-routing--adapter-isolation)
4. [Article Extraction & Boilerplate Removal Engine](#article-extraction--boilerplate-removal-engine)
5. [Comment Extraction Engine Specifications](#comment-extraction-engine-specifications)
   - [Yahoo News Nexus GraphQL Gateway Architecture](#yahoo-news-nexus-graphql-gateway-architecture)
   - [MSN Peregrine & Community REST API Architecture](#msn-peregrine--community-rest-api-architecture)
6. [Candidate Discovery Engine Specifications](#candidate-discovery-engine-specifications)
   - [Pagination Scaling Formula](#pagination-scaling-formula)
   - [Per-Source Early Stopping](#per-source-early-stopping)
   - [Link Cleaning & Tracking Parameter Stripping](#link-cleaning--tracking-parameter-stripping)
   - [Programmatic vs. GUI Date Handling](#programmatic-vs-gui-date-handling)
7. [PyInstaller Standalone Executable Packaging](#pyinstaller-standalone-executable-packaging)
   - [Windowed Onefile Architecture](#windowed-onefile-architecture)
   - [Playwright & Chromium Bundling](#playwright--chromium-bundling)
   - [Frozen Runtime stdio Fallback Mechanism](#frozen-runtime-stdio-fallback-mechanism)
   - [Rebuilding the Executable](#rebuilding-the-executable)
8. [Testing Suite & Environment Considerations](#testing-suite--environment-considerations)
   - [Anaconda Tcl/Tk Fix (`tests/conftest.py`)](#anaconda-tcltk-fix-testsconftestpy)
   - [Running the Test Suite](#running-the-test-suite)
9. [Ethical Scraping & Scope Boundaries](#ethical-scraping--scope-boundaries)
10. [Documentation Links](#documentation-links)

---

## Architecture & Component Design

The application follows an **Adapter-Based Architecture**. Source-specific extraction rules (Yahoo, MSN) are isolated within dedicated adapters, while shared pipeline components handle candidate discovery, data routing, validation, rate limiting, dataset export, and GUI presentation.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        Graphical User Interface                         │
│                         (src.gui.app / CustomTkinter)                   │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────┐
│     Candidate Discovery Engine        │ │   Article Collector Engine    │
│      (src.discovery.search)           │ │  (src.collectors.pipeline)    │
└───────────────────┬───────────────────┘ └───────────────┬───────────────┘
                    │                                     │
                    ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Source Router                              │
│                         (src.collectors.router)                         │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────┐
│             YahooAdapter              │ │          MSNAdapter           │
│      (src.adapters.yahoo_adapter)     │ │   (src.adapters.msn_adapter)  │
└───────────────────┬───────────────────┘ └───────────────┬───────────────┘
                    │                                     │
                    ▼                                     ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────┐
│      Yahoo Nexus GraphQL Gateway      │ │   MSN Peregrine / Community   │
│      (src.comments.yahoo_graphql)     │ │   (src.comments.msn_api)      │
└───────────────────────────────────────┘ └───────────────────────────────┘
```

---

## Data Models & Schema Contracts

Core data structures are defined as strongly typed dataclasses in `src/models/`:

- **`Article`** (`src/models/article.py`):
  - `platform`: Name of the target source (`Yahoo`, `MSN`).
  - `requested_url`: Original URL submitted to the collector.
  - `canonical_url`: Canonical URL parsed from page metadata.
  - `title`: Article title.
  - `author`: Article author or publishing organization.
  - `publication_datetime`: ISO-8601 publication timestamp.
  - `article_text`: Full cleaned body text.
  - `comments_status`: Normalized status (`AVAILABLE`, `NONE_PRESENT`, `DISABLED`, `LOGIN_REQUIRED`, etc.).
  - `comment_count_reported`: Number of comments reported by page metadata or API.
  - `comments_collected`: Actual count of extracted comment records.
  - `comments`: List of root `Comment` dataclass instances.
  - `extraction_method`: Primary extraction strategy used (`structured_metadata`, `semantic_html`, `rendered_dom`).

- **`Comment`** (`src/models/comment.py`):
  - `comment_id`: Unique identifier for the comment.
  - `article_url`: Parent article URL.
  - `parent_comment_id`: ID of parent comment (for nested replies) or `None` (for top-level comments).
  - `author_display_name`: Display name of commenter.
  - `comment_text`: Full text of the comment.
  - `published_datetime`: ISO-8601 publication timestamp.
  - `reactions`: Dictionary of user reaction counts (e.g., likes, upvotes).
  - `reply_count`: Number of direct child replies.
  - `depth`: Nesting depth level (0 = top-level, 1 = direct reply, etc.).
  - `replies`: List of nested child `Comment` instances.

- **`CandidateArticle`** (`src/discovery/models.py`):
  - Represents an uncollected article candidate discovered during search.

---

## Source Routing & Adapter Isolation

URL recognition and adapter dispatch are managed by `SourceRouter` (`src/collectors/router.py`).

1. `SourceRouter` evaluates input URLs using regular expressions.
2. If matched, it delegates execution to the registered `BaseAdapter` instance (`YahooAdapter` or `MSNAdapter`).
3. Adding support for a new website requires creating a new adapter class inheriting from `BaseAdapter` (`src/adapters/base_adapter.py`) without altering existing adapters or export logic.

---

## Article Extraction & Boilerplate Removal Engine

Article body extraction follows a 4-tier fallback sequence (`src/extraction/article_text.py`):

1. **Structured Metadata**: `application/ld+json`, OpenGraph (`og:description`), and standard meta tags.
2. **Semantic HTML**: `<article>`, `<main>`, `itemprop="articleBody"`, and semantic paragraph structures.
3. **Source-Specific Selectors**: Platform container rules.
4. **Rendered DOM**: Browser rendering via Playwright for JavaScript-hydrated pages.

### Boilerplate Removal Rules

Article text extraction applies structural DOM filtering followed by targeted text-based guardrails:

- **Yahoo Boilerplate Filtering**:
  - Removes copyright notices, generic site navigation footers, social sharing bars, and "Read more on Yahoo" promotional blocks.
  - Removes metadata tags and topic keyword blocks when enclosed in structural metadata containers (`.article-tags`, `[data-component="Tags"]`).
- **MSN Boilerplate Filtering**:
  - Structural removal of partner site footers, embedded advertisement frames, and related slideshow carousels.
  - Structural and text-guardrail removal of promotional callouts such as *"READ ON THE FOX BUSINESS APP"* and publisher app link banners.

---

## Comment Extraction Engine Specifications

### Yahoo News Nexus GraphQL Gateway Architecture

Yahoo News delivers public user comments via the unauthenticated **Yahoo Nexus GraphQL Gateway API** (`src/comments/yahoo_graphql.py`).

- **Endpoint URL**: `https://nexus-gateway-prod.media.yahoo.com/graphql`
- **Authentication**: Unauthenticated public GraphQL queries using persisted query hashes.
- **Persisted Query Hashes**:
  - **`ycp_GetConversationWithMultipleContents_v1.2.0`**: Fetches initial conversation details, comment count, and top-level comment threads.
  - **`ycp_GetCommentReplies_v1.4.16`**: Fetches nested reply threads for a specific top-level comment ID.
- **Context Resolution**: The collector extracts the required `spaceId`, `contextToken`, and `uuid` parameters dynamically from rendered Yahoo article HTML (`window.INITIAL_STATE` or inline JSON scripts).

### MSN Peregrine & Community REST API Architecture

MSN delivers public comments via unauthenticated REST endpoints (`src/comments/msn_api.py`).

- **Endpoints**:
  - `https://assets.msn.com/service/MSN/Peregrine/community/v1/...`
  - `https://assets.msn.com/service/community/comments/`
- **Authentication**: Public REST requests with standard browser headers.
- **Context Resolution**: The collector extracts MSN article page identifiers (`contentId`, `pageId`, `activityId`) dynamically from the article HTML and metadata attributes to instantiate comment thread queries.

---

## Candidate Discovery Engine Specifications

Candidate Discovery (`src/discovery/search.py`) searches news articles using Bing News RSS and enforces source balancing, keyword filtering, and candidate deduplication.

### Pagination Scaling Formula

The discovery engine dynamically calculates the target number of RSS pagination pages per source based on the requested `max_candidates`:

```python
target_pages_per_source = min(5, max(2, math.ceil(max_candidates / 8)))
```

Offsets requested for each page follow the formula `first = 1 + 10 * i`:

| Max Candidates Setting | Target Pages / Source | RSS Offsets Requested |
| :--- | :--- | :--- |
| **10** | 2 | `first=1`, `first=11` |
| **20** | 3 | `first=1`, `first=11`, `first=21` |
| **30** | 4 | `first=1`, `first=11`, `first=21`, `first=31` |
| **40 or more** | 5 (max cap) | `first=1`, `first=11`, `first=21`, `first=31`, `first=41` |

### Per-Source Early Stopping

During RSS iteration for a given source:
- If an RSS offset query returns **0 new unique candidates**, the engine immediately terminates pagination for that source.
- This prevents unnecessary network calls when a query yields fewer results than the requested limit.

### Link Cleaning & Tracking Parameter Stripping

Discovered URLs pass through `clean_tracking_params()` (`src/discovery/search.py`):
- Unwraps Bing News RSS redirect wrappers (`apiclick.aspx?url=...`).
- Strips analytics tracking parameters (`utm_source`, `utm_medium`, `gclid`, `ncid`, `fbclid`, `guccounter`, etc.) while retaining functional query parameters required for article resolution.

### Programmatic vs. GUI Date Handling

- **API-Level Parameters**: The `CandidateDiscoverer.discover()` method accepts optional `start_date` and `end_date` arguments (`YYYY-MM-DD`). When supplied programmatically, candidates with missing or out-of-range publication dates are conservatively excluded.
- **Final GUI Design**: The desktop GUI intentionally omits user date range input fields because Bing News RSS does not support reliable historical date range queries. Instead, the GUI parses publication dates returned in RSS items and displays the observed available date range of the result set (e.g., *"Available dates in this search: 2026-09-20 to 2026-09-26"*).

---

## PyInstaller Standalone Executable Packaging

### Windowed Onefile Architecture

The standalone executable (`dist/NewsArticleCollector.exe`) is packaged using PyInstaller in single-file mode (`onefile`) with windowed mode enabled (`console=False` / `--noconsole`).

- **Spec File**: `NewsArticleCollector.spec`
- **Target Executable**: `dist/NewsArticleCollector.exe`
- **Embedded Environment**: Packages a bundled Python runtime alongside application modules and Playwright binaries.

### Playwright & Chromium Bundling

The executable bundles application code and the Playwright Chromium browser driver:
- `playwright/driver/package/.local-browsers/` is included inside the PyInstaller payload.
- At runtime, PyInstaller extracts assets to a temporary directory (`sys._MEIPASS`). `main.py` configures the `PLAYWRIGHT_BROWSERS_PATH` environment variable to point to `sys._MEIPASS` so Playwright reuses the bundled Chromium binary without requiring external downloads.

### Frozen Runtime stdio Fallback Mechanism

When PyInstaller executes in windowed mode (`console=False`), standard I/O streams (`sys.stdout`, `sys.stderr`, `sys.stdin`) are set to `None` by Windows `runw.exe`. Because Playwright's NodeJS driver relies on standard file descriptor operations, invoking Playwright under windowed mode can result in `AttributeError: 'NoneType' object has no attribute 'write'`.

To prevent crashes, `main.py` reassigns `None` stdio streams to memory buffer fallbacks at startup:

```python
import sys
import io

if getattr(sys, 'frozen', False):
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    if sys.stdin is None:
        sys.stdin = io.BytesIO()
```

### Rebuilding the Executable

To rebuild the executable:

```powershell
# Activate virtual environment
.venv\Scripts\activate

# Clean previous build artifacts
Remove-Item -Recurse -Force build, dist

# Run PyInstaller using the project spec file
pyinstaller NewsArticleCollector.spec
```

The output executable will be created at `dist/NewsArticleCollector.exe`.

---

## Testing Suite & Environment Considerations

### Anaconda Tcl/Tk Fix (`tests/conftest.py`)

When running `pytest` in Anaconda Python environments on Windows, missing or unconfigured `TCL_LIBRARY` and `TK_LIBRARY` environment variables can cause `_tkinter.TclError` during GUI component instantiation.

`tests/conftest.py` resolves this by detecting Anaconda installation paths and injecting valid Tcl/Tk library directory paths prior to test execution:

```python
import os
import sys

if hasattr(sys, 'prefix'):
    tcl_dir = os.path.join(sys.prefix, 'Library', 'lib', 'tcl8.6')
    tk_dir = os.path.join(sys.prefix, 'Library', 'lib', 'tk8.6')
    if os.path.exists(tcl_dir) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.exists(tk_dir) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_dir
```

### Running the Test Suite

Execute the complete test suite using pytest:

```powershell
python -m pytest tests/
```

---

## Ethical Scraping & Scope Boundaries

1. **No Protection Bypass**: The collector strictly respects website access controls and does not implement CAPTCHA solvers, proxy rotation, paywall bypasses, or stealth evasion mechanisms.
2. **Public Data Only**: Collects only content available through normal public browsing.
3. **Rate Limiting**: Enforces a minimum delay (1.5 seconds) between HTTP requests to prevent server overloading.

---

## Documentation Links

- 🏠 **[Project README](README.md)**: Overview and quick start.
- 📖 **[User Guide](USER_GUIDE.md)**: Operational guide and end-user manual.
