# Developer & Technical Architecture Guide

This document provides complete technical documentation for developers, software maintainers, and researchers modifying or extending the **Adaptive News Article and Comment Collector**.

---

## Table of Contents

1. [Architecture & Component Design](#architecture--component-design)
2. [Source Scope & Adapter Isolation](#source-scope--adapter-isolation)
   - [Primary Active Sources (Yahoo News & MSN)](#primary-active-sources-yahoo-news--msn)
   - [Internal & Extension Adapters (Blog & Civic Modules)](#internal--extension-adapters-blog--civic-modules)
3. [Data Models & Schema Contracts](#data-models--schema-contracts)
4. [Article Extraction & Boilerplate Removal Engine](#article-extraction--boilerplate-removal-engine)
5. [Comment Extraction Engine Specifications](#comment-extraction-engine-specifications)
   - [Yahoo News Nexus GraphQL Gateway Architecture](#yahoo-news-nexus-graphql-gateway-architecture)
   - [MSN Peregrine & Community REST API Architecture](#msn-peregrine--community-rest-api-architecture)
   - [Shared WordPress Comment Extraction Engine](#shared-wordpress-comment-extraction-engine)
6. [Candidate Discovery Engine Specifications](#candidate-discovery-engine-specifications)
   - [Independent Source Quotas & RSS Keyset Pagination](#independent-source-quotas--rss-keyset-pagination)
   - [Legacy Pagination Scaling Formula](#legacy-pagination-scaling-formula)
   - [Supabase URL Checker & Snapshot Caching](#supabase-url-checker--snapshot-caching)
   - [Per-Source Early Stopping](#per-source-early-stopping)
   - [Link Cleaning & Tracking Parameter Stripping](#link-cleaning--tracking-parameter-stripping)
   - [Programmatic vs. GUI Date Handling](#programmatic-vs-gui-date-handling)
7. [PyInstaller Standalone Executable Packaging](#pyinstaller-standalone-executable-packaging)
   - [Windowed Onefile Architecture](#windowed-onefile-architecture)
   - [Dynamic Playwright & Chromium Resolution (`browsers.json`)](#dynamic-playwright--chromium-resolution-browsersjson)
   - [Frozen Runtime stdio Fallback Mechanism (`os.devnull`)](#frozen-runtime-stdio-fallback-mechanism-osdevnull)
   - [Rebuilding the Executable](#rebuilding-the-executable)
8. [Testing Suite & Environment Considerations](#testing-suite--environment-considerations)
   - [Anaconda Tcl/Tk Fix (`tests/conftest.py`)](#anaconda-tcltk-fix-testsconftestpy)
   - [Local Configuration Isolation in Tests](#local-configuration-isolation-in-tests)
   - [Running the Test Suite](#running-the-test-suite)
9. [Supabase Integration & Staging Architecture](#supabase-integration--staging-architecture)
   - [Key Design Principles](#key-design-principles)
   - [Desktop GUI Staging Preview (`src/gui/supabase_preview.py`)](#desktop-gui-staging-preview-srcguisupabase_previewpy)
   - [Direct Supabase Upload Architecture (`src/integrations/supabase/uploader.py`)](#direct-supabase-upload-architecture-srcintegrationssupabaseuploaderpy)
10. [Documentation Links](#documentation-links)

---

## Architecture & Component Design

The application follows an **Adapter-Based Architecture**. Source-specific extraction rules are isolated within dedicated adapters, while shared pipeline components handle candidate discovery, data routing, validation, rate limiting, dataset export, and GUI presentation.

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
        ┌───────────┴───────────┐         ┌───────────┴───────────┐
        ▼                       ▼         ▼                       ▼
┌───────────────┐       ┌───────────────┐ ┌───────────────────────────────┐
│ YahooAdapter  │       │  MSNAdapter   │ │ Internal Extension Adapters   │
│ (src.collect- │       │ (src.collect- │ │ (TESL, HEPI, EngagementHQ,    │
│  ors.yahoo)   │       │  ors.msn)     │ │  Cult of Pedagogy, Spencer,   │
└───────┬───────┘       └───────┬───────┘ │  Wonkhe, Granicus, Legistar)  │
        │                       │         └───────────────────────────────┘
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│ Yahoo Nexus   │       │ MSN Peregrine │
│ GraphQL API   │       │ Community REST│
└───────────────┘       └───────────────┘
```

---

## Source Scope & Adapter Isolation

URL recognition and adapter dispatch are managed by `SourceRouter` ([`src/collectors/router.py`](src/collectors/router.py)).

### Primary Active Sources (Yahoo News & MSN)
- **`YahooAdapter`** ([`src/collectors/yahoo.py`](src/collectors/yahoo.py)): Handles Yahoo News URL recognition, fallback metadata extraction, cleaned article text extraction, and Nexus GraphQL comment extraction.
- **`MSNAdapter`** ([`src/collectors/msn.py`](src/collectors/msn.py)): Handles MSN News URL recognition, canonical syndication extraction, cleaned article body extraction, and Peregrine/Community REST comment extraction.
- Both adapters are actively exposed in the GUI, participate in automated Candidate Discovery, and have been validated against live websites.

### Internal & Extension Adapters (Blog & Civic Modules)
The repository contains 8 additional adapters additively registered in `SourceRouter`:
- **`TESLOntarioAdapter`** ([`src/collectors/tesl_ontario.py`](src/collectors/tesl_ontario.py)): WordPress educational blog adapter parsing reader discussions.
- **`HEPIAdapter`** ([`src/collectors/hepi.py`](src/collectors/hepi.py)): Higher education policy reports and public guest commentary.
- **`EngagementHQAdapter`** ([`src/collectors/engagement_hq.py`](src/collectors/engagement_hq.py)): Civic engagement consultations and resident submissions.
- **`CultOfPedagogyAdapter`** ([`src/collectors/cult_of_pedagogy.py`](src/collectors/cult_of_pedagogy.py)): Educational blog adapter with nested comment parsing.
- **`SpencerEducationAdapter`** ([`src/collectors/spencer_education.py`](src/collectors/spencer_education.py)): Educational foundation blog commentary.
- **`WonkheAdapter`** ([`src/collectors/wonkhe.py`](src/collectors/wonkhe.py)): Next.js SSR higher education policy articles and reader comments.
- **`GranicusIdeasAdapter`** ([`src/collectors/granicus_ideas.py`](src/collectors/granicus_ideas.py)): Civic agenda items and multi-page public comments from `*.granicusideas.com`.
- **`LegistarAdapter`** ([`src/collectors/legistar.py`](src/collectors/legistar.py)): Legislative management portal adapter with REST API discovery services (`LegistarDiscovery`).

**Operational Status Notice**: These 8 adapters are internal backend implementations. They are **not** selectable sources in the Candidate Discovery GUI, are **not** part of the active collection workflow, and are tested strictly against offline static HTML/JSON fixtures.

---

## Data Models & Schema Contracts

Core data structures are defined as strongly typed dataclasses and Pydantic models in `src/models/` and `src/discovery/models.py`:

- **`Article`** ([`src/models/article.py`](src/models/article.py)):
  - `platform`: Target source identifier (`Yahoo`, `MSN`, etc.).
  - `requested_url`: Original URL submitted to the collector.
  - `canonical_url`: Canonical URL parsed from page metadata.
  - `title`: Extracted headline.
  - `author`: Article author or publishing organization.
  - `publication_datetime`: ISO-8601 publication timestamp.
  - `article_text`: Full cleaned body text.
  - `comments_status`: Normalized status (`AVAILABLE`, `NONE_PRESENT`, `DISABLED`, `LOGIN_REQUIRED`, etc.).
  - `comment_count_reported`: Number of comments reported by metadata or API.
  - `comments_collected`: Actual count of extracted comment records.
  - `comments`: List of root `Comment` dataclass instances.
  - `extraction_method`: Primary extraction strategy used (`structured_metadata`, `semantic_html`, `rendered_dom`).

- **`Comment`** ([`src/models/comment.py`](src/models/comment.py)):
  - `comment_id`: Unique identifier for the comment.
  - `article_url`: Parent article URL.
  - `parent_comment_id`: ID of parent comment (for nested replies) or `None` (for top-level comments).
  - `author_display_name`: Display name of commenter.
  - `comment_text`: Full text of the comment.
  - `published_datetime`: ISO-8601 publication timestamp.
  - `reactions`: Dictionary of user reaction counts (e.g. upvotes).
  - `reply_count`: Number of direct child replies.
  - `depth`: Nesting depth level (0 = top-level, 1 = direct reply, etc.).
  - `replies`: List of nested child `Comment` instances.

- **`CandidateArticle`** ([`src/discovery/models.py`](src/discovery/models.py)):
  - Dataclass representing an uncollected candidate article discovered during Bing News RSS discovery queries, including URL, platform, headline, publication date, domain, and verification status (`is_verified_new`).

---

## Article Extraction & Boilerplate Removal Engine

Article body extraction follows a 4-tier fallback sequence ([`src/extraction/article_text.py`](src/extraction/article_text.py)):

1. **Structured Metadata**: `application/ld+json`, OpenGraph (`og:description`), and standard meta tags.
2. **Semantic HTML**: `<article>`, `<main>`, `itemprop="articleBody"`, and semantic paragraph structures.
3. **Source-Specific Selectors**: Platform container rules.
4. **Rendered DOM**: Browser rendering via Playwright ([`src/browser/manager.py`](src/browser/manager.py)) for JavaScript-hydrated pages.

### Boilerplate Removal Rules
- **Yahoo Boilerplate Filtering**:
  - Removes copyright notices, generic site navigation footers, social sharing bars, and "Read more on Yahoo" promotional blocks.
  - Removes metadata tags and topic keyword blocks when enclosed in structural metadata containers (`.article-tags`, `[data-component="Tags"]`).
- **MSN Boilerplate Filtering**:
  - Structural removal of partner site footers, embedded advertisement frames, and related slideshow carousels.
  - Structural and text-guardrail removal of promotional callouts such as *"READ ON THE FOX BUSINESS APP"* and publisher app link banners.

---

## Comment Extraction Engine Specifications

### Yahoo News Nexus GraphQL Gateway Architecture
Yahoo News delivers public user comments via the unauthenticated **Yahoo Nexus GraphQL Gateway API** ([`src/extraction/comments.py`](src/extraction/comments.py)).
- **Endpoint URL**: `https://nexus-gateway-prod.media.yahoo.com/graphql`
- **Authentication**: Unauthenticated public GraphQL queries using persisted query hashes.
- **Persisted Query Hashes**:
  - `ycp_GetConversationWithMultipleContents_v1.2.0`: Fetches initial conversation details, comment count, and top-level comment threads.
  - `ycp_GetCommentReplies_v1.4.16`: Fetches nested reply threads for a specific top-level comment ID.
- **Context Resolution**: The `YahooCommentExtractor` class extracts the required `spaceId`, `contextToken`, and article UUID dynamically from rendered Yahoo article HTML (`window.INITIAL_STATE` or inline JSON scripts).

### MSN Peregrine & Community REST API Architecture
MSN delivers public comments via unauthenticated REST endpoints ([`src/collectors/msn.py`](src/collectors/msn.py) and [`src/extraction/comments.py`](src/extraction/comments.py)).
- **Endpoints**:
  - `https://assets.msn.com/service/MSN/Peregrine/community/v1/...`
  - `https://assets.msn.com/service/community/comments/`
- **Authentication**: Public REST requests with standard browser headers.
- **Context Resolution**: The collector extracts MSN article page identifiers (`contentId`, `pageId`, `activityId`) dynamically from article HTML and metadata attributes to instantiate comment thread queries.

### Shared WordPress Comment Extraction Engine
For WordPress-based sources ([`src/extraction/wordpress.py`](src/extraction/wordpress.py)), a centralized comment tree parser extracts nested discussions:
- Recursively traverses `<ol class="comment-list">` and `<ul class="children">`.
- Filters out pingbacks and trackbacks (`<li class="pingback">`, `<li class="trackback">`).
- Resolves hierarchical `parent_comment_id` links and calculates nesting `depth`.

---

## Candidate Discovery Engine Specifications

Candidate Discovery ([`src/discovery/search.py`](src/discovery/search.py)) discovers candidate articles using Bing News RSS and enforces source quotas, keyword filtering, and candidate deduplication.

### Independent Source Quotas & RSS Keyset Pagination
In the active default discovery mode, each enabled source (Yahoo News and MSN) has an independent candidate target quota (default: `50` each):
- RSS requests iterate across offset ranges (`first=1`, `first=11`, `first=21`, ...) up to 10 pages per source.
- Paginates each source until its specific target quota is achieved or candidate results are exhausted.

### Legacy Pagination Scaling Formula
When the user explicitly activates **"Legacy Combined Max:"** mode, the discovery engine switches to a single combined candidate ceiling and calculates target pages dynamically:
```python
target_pages_per_source = min(5, max(2, math.ceil(max_candidates / 8)))
```

### Supabase URL Checker & Snapshot Caching
The discovery engine integrates `SupabaseUrlChecker` ([`src/integrations/supabase/url_checker.py`](src/integrations/supabase/url_checker.py)):
- **Read-Only Snapshot**: When Supabase duplicate checking is enabled, the checker loads a read-only snapshot of existing URLs from Supabase `public.articles`.
- **Duplicate Exclusion**: Candidate URLs that match existing stored records are filtered out. Excluded URLs are recorded in discovery diagnostics and excluded from the final selection table.
- **Candidate Verification Column**: Candidates presented in the preview table display a `DB Status` of `"New"` (if verified absent from Supabase) or `"Unverified"` (if duplicate checking was bypassed).

### Per-Source Early Stopping
During RSS iteration for a given source:
- If an RSS offset query returns **0 new unique candidates**, the engine terminates pagination for that source immediately to prevent redundant network calls.

### Link Cleaning & Tracking Parameter Stripping
Discovered URLs pass through `clean_tracking_params()`:
- Unwraps Bing News RSS redirect wrappers (`apiclick.aspx?url=...`).
- Strips analytics tracking parameters (`utm_source`, `utm_medium`, `gclid`, `ncid`, `fbclid`, `guccounter`, etc.) while retaining functional parameters required for article resolution.

### Programmatic vs. GUI Date Handling
- **API-Level Parameters**: `CandidateDiscoverer.discover()` accepts optional `start_date` and `end_date` arguments (`YYYY-MM-DD`).
- **GUI Feedback**: The desktop GUI intentionally omits user date range input fields because external news RSS providers do not support reliable historical date filtering. Instead, the GUI parses publication dates in returned items and displays the observed date range of the result set.

---

## PyInstaller Standalone Executable Packaging

### Windowed Onefile Architecture
The standalone executable (`NewsArticleCollector.exe`) is packaged using PyInstaller in single-file mode (`onefile`) with windowed mode enabled (`console=False`).
- **Spec File**: `NewsArticleCollector.spec`
- **Output Binary**: `dist-new/NewsArticleCollector.exe` (~334 MB)

### Dynamic Playwright & Chromium Resolution (`browsers.json`)
The packaging specification dynamically inspects Playwright's installed `browsers.json` to bundle only the active browser revisions required for execution:
- Identifies the specific active revisions of standard Chromium (`chromium-<rev>`) and Chromium Headless Shell (`chromium_headless_shell-<rev>`).
- Excludes outdated browser revisions and unrelated browsers (Firefox, WebKit), reducing payload size from >1.3 GB to ~334 MB while ensuring both headless and headed modes function reliably.

### Frozen Runtime stdio Fallback Mechanism (`os.devnull`)
Under Windows windowed execution (`console=False`), standard I/O streams are set to `None`. Because Playwright's NodeJS driver requires valid file descriptors, `main.py` redirects invalid stdio streams to `os.devnull` at startup:
```python
if getattr(sys, 'frozen', False):
    # Redirect missing stdio streams to os.devnull for windowed GUI mode (console=False)
    if sys.stdout is None or getattr(sys.stdout, 'fileno', lambda: -1)() < 0:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None or getattr(sys.stderr, 'fileno', lambda: -1)() < 0:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None or getattr(sys.stdin, 'fileno', lambda: -1)() < 0:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")

    # Resolve PyInstaller temporary extraction directory for bundled Playwright browsers
    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
    bundled_browsers = os.path.join(base_dir, "ms-playwright")
    if os.path.exists(bundled_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browsers

    # Set working directory to the executable's directory so output persists next to the EXE
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(exe_dir)
```

### Rebuilding the Executable
To rebuild the standalone executable from source, activate the appropriate Python build environment first (ensuring dependencies and PyInstaller are installed), then run the build command using the isolated `dist-new` and `build-new` directories:
```powershell
# 1. Activate the appropriate Python build environment
.venv\Scripts\activate

# 2. Run PyInstaller with isolated output directories
python -m PyInstaller --clean --distpath dist-new --workpath build-new NewsArticleCollector.spec
```

The resulting verified executable will be generated at `dist-new/NewsArticleCollector.exe`.

---

## Testing Suite & Environment Considerations

### Anaconda Tcl/Tk Fix (`tests/conftest.py`)
In Anaconda Python environments on Windows, missing or unconfigured `TCL_LIBRARY` and `TK_LIBRARY` environment variables can trigger `_tkinter.TclError` during test startup. `tests/conftest.py` automatically detects Anaconda library paths and injects valid environment variables prior to test execution.

### Local Configuration Isolation in Tests
When testing configuration loaders (`src/integrations/supabase/config.py`), tests should isolate `config_dir` or mock `data/config/supabase_client_config.json` so test assertions do not depend on the presence or absence of local user configuration on disk.

### Running the Test Suite
Execute tests using pytest:
```powershell
python -m pytest tests/
```

---

## Supabase Integration & Staging Architecture

The Supabase Compatibility and Staging Layer ([`src/integrations/supabase/`](src/integrations/supabase/)) decouples internal collection models from the database storage schema.

### Key Design Principles
1. **Adapter-Independent Staging**: Collector adapters continue producing rich internal `Article` and `Comment` models. `SupabaseMapper` converts these models into `SupabaseArticleRow` and `SupabaseCommentRow` staging objects.
2. **Globally Unique Negative Staging IDs**: Temporary article IDs (`-1`, `-2`, ...) and comment IDs (`-1`, `-2`, `-3`, ...) use negative integer values to guarantee zero collision with positive database identity values generated by Supabase during future insertions.
3. **Article-Scoped Two-Pass Parent Resolution**:
   - **Pass 1**: Traverses comment trees for an article, assigns global negative staging IDs, records `structural_parent_staging_id`, and builds an article-local source ID map.
   - **Pass 2**: Resolves `parent_comment_id` by checking explicit string `comment.parent_comment_id` in the local map first; if missing, falls back to `structural_parent_staging_id`.
4. **Database Default Omission Rules**: Fields with PostgreSQL defaults (`created_at` default `now()`, `is_relevant` default `true`) set to `None` in staging are omitted from future INSERT payloads so column defaults apply cleanly. AI fields (`processing_*`) are left `None`/NULL.
5. **SHA-256 Content Hashing**: Calculates a 64-character hexadecimal hash from normalized article body text (`compute_content_hash()`).
6. **Unique Index Enforcement**: `SupabaseValidator` validates staged datasets against unique indexes (`articles_url_unique_idx` and `articles_content_hash_unique_idx`).

### Desktop GUI Staging Preview (`src/gui/supabase_preview.py`)
- **Tab 4 ("Supabase Articles Staging")**: Treeview table presenting all 14 `public.articles` schema columns in contract order with full un-truncated text detail inspection panel.
- **Tab 5 ("Supabase Comments Staging")**: Treeview table presenting all 5 `public.comments` schema columns with full un-truncated text detail inspection panel.
- **Validation Status & Gated Export**: A status indicator in Section 4 displays staging validation state. The "Export Supabase CSVs..." button is enabled when the dataset is valid or contains warnings.

### Direct Supabase Upload Architecture (`src/integrations/supabase/uploader.py`)
- **Client-Safe Credentials**: Stores only public Project URL (`https://<ref>.supabase.co`) and Publishable/Anon Key in local `data/config/supabase_client_config.json` (git-ignored). Uses zero `service_role` keys.
- **Read-Only Pre-Upload Dry Run (`run_dry_run()`)**: Performs read-only GET queries prior to any database write. Guarantees ZERO write calls (POST/PATCH/DELETE) and classifies articles into Cases A-D:
  - **Case A**: New article and hash $\rightarrow$ Queued for insert.
  - **Case B**: URL and hash match same existing row $\rightarrow$ Mapped to existing ID; 0 article inserts needed.
  - **Case C**: URL matches but content hash differs $\rightarrow$ Conflict warning; insert prohibited.
  - **Case D**: URL matches row 1, hash matches row 2 $\rightarrow$ Ambiguous conflict; upload blocked.
- **Real Database ID Translation**: Translates temporary negative staging IDs (`-1`, `-101`) to returned positive database IDs (`1001`, `5001`) via ID maps.
- **Topological Level-Order Comment Insertion**: Root comments (`parent_comment_id is None`) are inserted first. Child replies are then inserted in level order using translated positive `parent_comment_id` values.
- **User-Only Execution Policy**: All live Supabase operations are performed personally by the user.

---

## Documentation Links

- 🏠 **[Project README](README.md)**: Overview, quick start, and system compatibility.
- 📖 **[User Guide](USER_GUIDE.md)**: Operational guide and desktop user manual.
- 📋 **[Agent Rules](AGENTS.md)**: Engineering governance, approval gates, and source boundaries.
- 🗄️ **[Archived Project Plan](docs/archive/PLAN.md)**: Original prototype specification (Steps 1–26).
- 🗄️ **[Archived Build Steps](docs/archive/BUILD_STEPS.md)**: Historical implementation log (Steps 1–31).
