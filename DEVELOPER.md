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
   - [Frozen Runtime stdio Fallback Mechanism (`os.devnull`)](#frozen-runtime-stdio-fallback-mechanism-osdevnull)
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
│                       (src.gui.app / Tkinter / TTK)                     │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────┐
│     Candidate Discovery Engine        │ │   Article Collector Engine    │
│      (src.discovery.search)           │ │   (src.collectors.batch)      │
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
│       (src.collectors.yahoo)          │ │       (src.collectors.msn)    │
└───────────────────┬───────────────────┘ └───────────────┬───────────────┘
                    │                                     │
                    ▼                                     ▼
┌───────────────────────────────────────┐ ┌───────────────────────────────┐
│      Yahoo Nexus GraphQL Gateway      │ │   MSN Peregrine / Community   │
│      (src.extraction.comments)        │ │  (src.collectors.msn &        │
│                                       │ │   src.extraction.comments)    │
└───────────────────────────────────────┘ └───────────────────────────────┘
```

---

## Data Models & Schema Contracts

Core data structures are defined as strongly typed dataclasses and Pydantic models in `src/models/` and `src/discovery/models.py`:

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
  - Dataclass representing an uncollected candidate article discovered during Bing News RSS discovery queries.

---

## Source Routing & Adapter Isolation

URL recognition and adapter dispatch are managed by `SourceRouter` (`src/collectors/router.py`).

1. `SourceRouter` evaluates input URLs using regular expressions.
2. If matched, it delegates execution to the registered `BaseAdapter` subclass (`YahooAdapter` in `src/collectors/yahoo.py` or `MSNAdapter` in `src/collectors/msn.py`).
3. Adding support for a new website requires creating a new adapter class inheriting from `BaseAdapter` (`src/collectors/base.py`) without altering existing adapters or export logic.

---

## Article Extraction & Boilerplate Removal Engine

Article body extraction follows a 4-tier fallback sequence (`src/extraction/article_text.py`):

1. **Structured Metadata**: `application/ld+json`, OpenGraph (`og:description`), and standard meta tags.
2. **Semantic HTML**: `<article>`, `<main>`, `itemprop="articleBody"`, and semantic paragraph structures.
3. **Source-Specific Selectors**: Platform container rules.
4. **Rendered DOM**: Browser rendering via Playwright (`src/browser/manager.py`) for JavaScript-hydrated pages.

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

Yahoo News delivers public user comments via the unauthenticated **Yahoo Nexus GraphQL Gateway API** (`src/extraction/comments.py`).

- **Endpoint URL**: `https://nexus-gateway-prod.media.yahoo.com/graphql`
- **Authentication**: Unauthenticated public GraphQL queries using persisted query hashes.
- **Persisted Query Hashes**:
  - **`ycp_GetConversationWithMultipleContents_v1.2.0`**: Fetches initial conversation details, comment count, and top-level comment threads.
  - **`ycp_GetCommentReplies_v1.4.16`**: Fetches nested reply threads for a specific top-level comment ID.
- **Context Resolution**: The `YahooCommentExtractor` class extracts the required `spaceId`, `contextToken`, and article UUID dynamically from rendered Yahoo article HTML (`window.INITIAL_STATE` or inline JSON scripts).

### MSN Peregrine & Community REST API Architecture

MSN delivers public comments via unauthenticated REST endpoints (`src/collectors/msn.py` and `src/extraction/comments.py`).

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

The standalone executable (`NewsArticleCollector.exe`) is packaged using PyInstaller in single-file mode (`onefile`) with windowed mode enabled (`console=False` / `--noconsole`).

- **Spec File**: `NewsArticleCollector.spec`
- **Target Executable**: `dist/NewsArticleCollector.exe`
- **Embedded Environment**: Packages a bundled Python runtime alongside application modules and Playwright binaries.

### Playwright & Chromium Bundling

The executable spec file (`NewsArticleCollector.spec`) dynamically discovers host Playwright Chromium binaries:
- `user_ms_playwright = os.path.expanduser('~\\AppData\\Local\\ms-playwright')` is bundled into the `ms-playwright/` target path inside PyInstaller's payload (`sys._MEIPASS`).
- At startup, `main.py` resolves `bundled_browsers = os.path.join(sys._MEIPASS, "ms-playwright")` and sets `os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers` so Playwright reuses the bundled Chromium binary without requiring external downloads.

### Frozen Runtime stdio Fallback Mechanism (`os.devnull`)

When PyInstaller executes in windowed mode (`console=False`), standard I/O streams (`sys.stdout`, `sys.stderr`, `sys.stdin`) are set to `None` by Windows `runw.exe`. Because Playwright's NodeJS driver relies on valid file descriptors, invoking Playwright under windowed mode can result in `AttributeError: 'NoneType' object has no attribute 'write'`.

To prevent crashes, `main.py` inspects stream handles at startup and redirects invalid stdio streams to `os.devnull`:

```python
if getattr(sys, 'frozen', False):
    if sys.stdout is None or getattr(sys.stdout, 'fileno', lambda: -1)() < 0:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None or getattr(sys.stderr, 'fileno', lambda: -1)() < 0:
        sys.stderr = open(os.devnull, "r", encoding="utf-8")
    if sys.stdin is None or getattr(sys.stdin, 'fileno', lambda: -1)() < 0:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")

    # Set working directory to the executable's folder so outputs persist beside the EXE
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(exe_dir)
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

---

## Supabase Integration & Staging Architecture (`src/integrations/supabase/`)

The Supabase Compatibility and Staging Layer decouples the internal collection pipeline from the database storage schema contract defined in `Article and Comment Schemas from Supabase.xlsx`.

### Key Design Principles

1. **Adapter-Independent Staging**: Collector adapters continue producing rich internal `Article` and `Comment` models (preserving diagnostic notes, `comments_status`, reactions, depth, and display names). `SupabaseMapper` converts these models into `SupabaseArticleRow` and `SupabaseCommentRow` staging objects.
2. **Globally Unique Negative Staging IDs**: Temporary article IDs (`-1`, `-2`, ...) and comment IDs (`-1`, `-2`, `-3`, ...) use negative integer values to guarantee zero collision with positive database identity values generated by Supabase during future insertions. Comment staging IDs are maintained as a single continuous decreasing sequence across all articles in a dataset.
3. **Article-Scoped Two-Pass Parent Resolution & Structural Fallbacks**:
   - **Pass 1**: Traverses comment trees for an article, assigns global negative staging IDs, records `structural_parent_staging_id` during tree traversal, and builds an article-local source ID map. Detects duplicate source comment IDs within the article context, logs collision warnings, and uses collision-safe keying.
   - **Pass 2**: Resolves `parent_comment_id` by checking explicit string `comment.parent_comment_id` in the local map first; if missing or unresolvable, falls back to the `structural_parent_staging_id`.
4. **Database Default Omission Rules**: Fields with PostgreSQL defaults (`created_at` default `now()`, `is_relevant` default `true`) set to `None` in staging are omitted from future INSERT payloads so column defaults apply cleanly. AI fields (`processing_status`, `processing_note`, `processed_at`) are intentionally left `None`/NULL because no AI processing has occurred.
5. **SHA-256 Content Hashing**: `compute_content_hash()` calculates a 64-character lowercase hexadecimal hash from normalized article body text (stripping leading/trailing whitespace and replacing `\r\n` with `\n`).
6. **Unique Index Enforcement**: `SupabaseValidator` validates staged datasets against unique indexes (`articles_url_unique_idx` and `articles_content_hash_unique_idx`) and flags article-scoped duplicate source comment IDs.
7. **Supabase-Shaped Staging CSV Export**: `SupabaseCSVExporter` exports `articles_supabase.csv` and `comments_supabase.csv`. Because these files contain temporary negative staging IDs, they are classified as staging/export files used for staging, relationship inspection, and previewing, rather than direct raw database imports.
8. **Shared Database Safety Contract**: Unit tests never connect to the live Supabase database. Testing relies entirely on local mapping, local validation, and local CSV exports.

### Desktop GUI Supabase Staging Preview & Export Architecture (`src/gui/supabase_preview.py`)

Step 28 integrates the Supabase staging dataset directly into the desktop GUI presentation layer:
- **Presentation Helper Module (`src/gui/supabase_preview.py`)**: Isolates column formatting, text truncation, and un-truncated detail text rendering from core models and Tkinter widgets.
- **Tab 4 ("Supabase Articles Staging")**: Treeview display presenting all 14 `public.articles` schema columns in contract order (`id`, `title`, `content`, `source`, `created_at`, `url`, `author`, `published_date`, `content_hash`, `clean_content`, `processing_status`, `processing_note`, `processed_at`, `is_relevant`) with vertical/horizontal scrollbars and a bottom inspection panel rendering full un-truncated article text upon row selection.
- **Tab 5 ("Supabase Comments Staging")**: Treeview display presenting all 5 `public.comments` schema columns in contract order (`id`, `article_id`, `text`, `created_at`, `parent_comment_id`) with vertical/horizontal scrollbars and a bottom inspection panel rendering full un-truncated comment text upon row selection.
- **Validation Status & Gated Export**: A status indicator in Section 4 displays staging validation state (valid, warnings, or invalid errors). The "Export Supabase CSVs..." button is disabled when validation errors or an empty dataset are present, and enabled when the dataset is valid or contains warnings.
- **Additive Worker Thread Execution**: Staging creation occurs on the worker thread following standard collection and standard JSON/CSV export. If Supabase staging fails, the exception is caught, logged, and reported on the UI thread without interrupting or suppressing standard collection results, logs, or standard CSV/JSON output.
- **Custom Directory Export Prompt**: Clicking "Export Supabase CSVs..." prompts the user with a directory selection dialog (`filedialog.askdirectory`), enabling destination folder customization.

---

## Documentation Links

- 🏠 **[Project README](README.md)**: Overview and quick start.
- 📖 **[User Guide](USER_GUIDE.md)**: Operational guide and end-user manual.
