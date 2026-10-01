# BUILD_STEPS.md

## Adaptive News Article and Comment Collector

Complete these steps sequentially. The coding agent should stop after
each major step, report what changed, show test results, provide a detailed
end-of-step walkthrough (files created/modified, purpose, functionality, key code,
integration context, tests/results, limitations/issues, and next step preview),
and wait for approval before continuing unless explicitly instructed otherwise.

Steps 1–26 are completed. For Step 27 and all subsequent new build steps, a mandatory two-gate pre-implementation approval workflow applies (see the Workflow section before Step 27).

------------------------------------------------------------------------

## Phase 0 - Project Initialization

### Step 1 - Initialize the Project

Create: - `README.md` - `requirements.txt` - `.gitignore` - `src/` -
`data/input/` - `data/output/` - `data/diagnostics/` - `tests/`

Do not build scraper logic yet.

Acceptance: - project opens normally in Antigravity; - Python
environment is identified; - generated data and secrets are ignored by
Git.

------------------------------------------------------------------------

### Step 2 - Create and Verify Python Environment

Use Python 3.11+ if available.

Create a virtual environment:

    python -m venv .venv

Activate it on Windows PowerShell:

    .\.venv\Scripts\Activate.ps1

Install only the initial dependencies: - playwright - beautifulsoup4 -
pydantic (or dataclasses if preferred) - pytest

Then install Playwright Chromium:

    python -m playwright install chromium

Acceptance: - Python runs from `.venv`; - Playwright can launch
Chromium; - pytest executes.

------------------------------------------------------------------------

## Phase 1 - Core Data Model

### Step 3 - Define Normalized Models

Create Article, Comment, and extraction-result models.

Include the fields specified in `AGENTS.md`.

Create a `CommentStatus` enum: - AVAILABLE - NONE_PRESENT - DISABLED -
LOGIN_REQUIRED - NOT_LOADED - BLOCKED - UNSUPPORTED - UNKNOWN -
EXTRACTION_ERROR

Acceptance: - models instantiate correctly; - JSON serialization
works; - model tests pass.

------------------------------------------------------------------------

### Step 4 - Implement URL Validation and Source Router

Create a source router that: - validates URLs; - recognizes supported
Yahoo domains; - later recognizes MSN domains; - returns a clear
unsupported-source result.

Do not implement extraction yet.

Acceptance examples: - Yahoo URL -\> Yahoo adapter - malformed URL -\>
validation error - unsupported website -\> UNSUPPORTED

Add unit tests.

------------------------------------------------------------------------

## Phase 2 - Browser Layer

### Step 5 - Build Browser Manager

Create a reusable Playwright browser manager.

Requirements: - Chromium; - isolated context; - configurable
headed/headless mode; - reasonable navigation timeout; - conservative
delay configuration; - clean shutdown; - no personal browser
cookies/profile.

Detect and report: - timeout; - navigation error; - CAPTCHA/access
denial when identifiable.

Acceptance: - opens a public test page; - returns rendered HTML; -
closes browser cleanly.

------------------------------------------------------------------------

## Phase 3 - Yahoo Article Prototype

### Step 6 - Implement Yahoo URL Loading

Create `YahooAdapter`.

Initially support a single manually supplied Yahoo article URL.

Record: - requested URL; - final/canonical URL when available; -
HTTP/navigation outcome; - retrieval timestamp.

Acceptance: - a live Yahoo article can be loaded; - failures produce
useful diagnostics.

------------------------------------------------------------------------

### Step 7 - Extract Yahoo Article Metadata

Implement fallback extraction:

1.  JSON-LD
2.  OpenGraph/meta tags
3.  semantic HTML
4.  Yahoo-specific selectors if necessary

Extract when available: - title - author - publication date - updated
date - original publisher - canonical URL - language

Record which method supplied each important field when practical.

Acceptance: - test several Yahoo articles; - missing fields do not crash
the run; - no fabricated values.

------------------------------------------------------------------------

### Step 8 - Extract Yahoo Article Body

Extract the main article text while excluding: - navigation; -
advertisements; - recommendations; - unrelated footer text; - comment
text.

Normalize whitespace but preserve paragraph order.

Acceptance: - body contains the actual article; - obvious unrelated page
text is excluded; - empty extraction is reported as a failure/warning.

------------------------------------------------------------------------

## Phase 4 - Yahoo Comment Investigation

### Step 9 - Build Comment Diagnostics BEFORE Extraction

This step is deliberately investigative.

For each Yahoo article, record whether the rendered page contains: -
"comments" text/buttons; - "View comments" controls; - comment counts; -
likely comment containers; - iframes; - relevant rendered elements; -
access/login messages.

When diagnostics are enabled, optionally save: - rendered HTML; - a
screenshot; - a short structured diagnostic JSON file.

Do NOT claim that comments do not exist simply because a selector was
not found.

Acceptance: - running several Yahoo URLs produces a diagnostic report; -
each article receives a meaningful preliminary comment status.

STOP HERE and review the findings before implementing Yahoo comment
extraction.

------------------------------------------------------------------------

### Step 10 - Determine Yahoo's Current Comment Delivery Method

Using the diagnostic results, document: - how comments are opened; -
whether JavaScript is required; - whether an iframe is involved; -
whether public comment data appears in rendered DOM; - whether login is
required; - whether availability differs across articles.

Update the Yahoo adapter design based on observed evidence.

Do not implement bypasses for access controls.

Acceptance: - `README.md` or diagnostics contain the observed Yahoo
comment mechanism; - extraction strategy is based on current evidence,
not guessed selectors.

------------------------------------------------------------------------

### Step 11 - Implement Yahoo Public Comment Extraction

Only if Step 10 confirms publicly accessible comments.

Implement: - opening the legitimate comment interface; - waiting for
comment content; - extracting top-level comments; - extracting replies
when feasible; - configurable maximum comments; - deduplication.

Capture: - comment ID if available; - display name; - text; -
timestamp; - reactions; - reply count; - parent ID; - depth.

Acceptance: - at least one known comment-enabled article can be
collected; - zero collected comments are not mislabeled as
NONE_PRESENT; - results are normalized.

If Yahoo comments cannot currently be collected, document that
limitation and continue the project without fabricating a solution.

------------------------------------------------------------------------

## Phase 5 - Output

### Step 12 - JSON Export

Export one normalized result containing: - article; - comments; -
collection metadata; - comment status; - diagnostics summary.

Use UTF-8.

Acceptance: - exported JSON opens correctly; - Unicode text is
preserved; - comments remain associated with the article.

------------------------------------------------------------------------

### Step 13 - CSV Export

Create: - `articles.csv` - `comments.csv`

Use a stable article identifier to join the files.

Acceptance: - CSV files open correctly in Excel/Google Sheets; -
multiple comments map to the correct article; - commas/quotes/newlines
are escaped correctly.

------------------------------------------------------------------------

## Phase 6 - Batch Collection

### Step 14 - Multiple URL Input

Support: - repeated CLI URLs; - `data/input/urls.txt`.

For each URL: - route source; - collect; - export; - continue after
individual failures.

Acceptance: - one failed URL does not terminate the batch; - final
summary shows successes/failures.

------------------------------------------------------------------------

### Step 15 - Add Rate Limiting and Run Limits

Add configurable: - delay between pages; - maximum articles; - maximum
comments per article; - navigation timeout.

Defaults should be conservative.

Acceptance: - batch collection cannot accidentally run without
reasonable limits; - configuration is documented.

------------------------------------------------------------------------

### Step 16 - Create Collection Summary

After a run, display:

    Articles requested:
    Articles successfully extracted:
    Articles failed:
    Articles with comments available:
    Articles with no comments:
    Articles with unknown/inaccessible comments:
    Comments collected:
    Output location:

Acceptance: - summary matches exported data.

------------------------------------------------------------------------

## Phase 7 - MSN Adapter

### Step 17 - Investigate MSN Structure

Repeat the evidence-first process used for Yahoo.

Document: - URL patterns; - metadata structure; - article body
structure; - syndication/original publisher information; - current
comment availability/mechanism.

Do not assume MSN behaves like Yahoo.

------------------------------------------------------------------------

### Step 18 - Implement MSN Article Extraction

Implement MSN adapter using the same normalized Article model.

Acceptance: - router automatically selects MSN; - article output has the
same schema as Yahoo; - source-specific code remains inside MSN adapter.

------------------------------------------------------------------------

### Step 19 - Implement MSN Comment Handling

Based on Step 17 evidence: - detect comment availability; - collect
public comments if supported; - otherwise return an accurate status.

Acceptance: - same Comment model/status system works for Yahoo and MSN.

------------------------------------------------------------------------

## Phase 8 - Desktop Application

### Step 20 - Build Minimal GUI

Only begin after CLI collection is stable.

Suggested first UI: - URL text box; - multi-URL input/import; - source
shown automatically; - maximum comments field; - Start button; -
progress area; - results table; - status/error panel; - Export buttons.

Keep scraper logic outside the UI.

Acceptance: - GUI can invoke the existing collection engine; - closing
GUI shuts down browser cleanly; - UI remains responsive during
collection.

------------------------------------------------------------------------

## Mandatory Pre-Implementation Approval Workflow (Step 27 and Subsequent Steps)

Steps 1–26 are completed historical implementation milestones. For Step 27 and all subsequent new build steps, the coding agent must execute a mandatory two-gate approval workflow:

1. **Review**: Review `AGENTS.md`, `PLAN.md`, `BUILD_STEPS.md`, and the relevant existing implementation.
2. **Implementation Plan**: Produce a concise implementation plan before making any implementation changes. The plan must identify:
   - files expected to be created or modified;
   - classes/functions/components expected to be added or changed;
   - how the work integrates with the existing architecture;
   - testing and verification strategy;
   - important design decisions, assumptions, and risks;
   - anything explicitly out of scope for that step.
3. **Gate 1 Approval**: **STOP** and wait for explicit user approval of the implementation plan before making any code or configuration edits.
4. **Implementation**: Only after plan approval, implement that step.
5. **Testing & Verification**: Run the appropriate unit, integration, and smoke tests.
6. **Walkthrough**: Provide the comprehensive end-of-step walkthrough (per `AGENTS.md` Rule 2a).
7. **Gate 2 Approval**: **STOP** and wait for explicit user approval before proceeding to the next build step.

------------------------------------------------------------------------

### Step 21 - Add Research-Friendly Result View

Display per article: - platform; - title; - publisher; - publication
date; - article extraction status; - comment status; - reported comment
count; - collected count; - diagnostic note.

Acceptance: - user can quickly identify useful sponsor samples.

------------------------------------------------------------------------

## Phase 9 - Topic-Assisted Workflow

### Step 22 - Add Topic Field

Allow a topic such as:

    AI in Education

Initially use the topic as: - dataset metadata; - an optional
filter/label.

Do not mix search/discovery logic into source adapters.

------------------------------------------------------------------------

### Step 23 - Add Candidate Article Discovery

Evaluate an approved search/discovery method separately from scraping.

Workflow: 1. user enters topic; 2. discover candidate Yahoo/MSN URLs; 3.
display candidates; 4. user selects articles; 5. collector processes
them.

Acceptance: - discovery and extraction are separate modules; - URLs
retain discovery/source provenance.

------------------------------------------------------------------------

## Phase 10 - Testing and Documentation

### Step 24 - Add Parser Fixtures

Save small sanitized test fixtures where appropriate.

Test: - valid article; - missing author; - missing date; - no
comments; - inaccessible comments; - malformed URL; - changed/missing
selector; - duplicate comment.

Do not rely entirely on live websites.

------------------------------------------------------------------------

### Step 25 - Create Sponsor Sample

Use the application to collect a small AI-in-Education dataset.

Suggested target: - 3-5 Yahoo articles; - 3-5 MSN articles; - comments
where publicly available.

For each article document: - URL; - title; - publisher; - date; -
article extraction result; - comment status; - number of comments
collected; - limitations.

This is a research sample, not a large crawl.

------------------------------------------------------------------------

### Step 26 - Final Documentation

Update `README.md` with: - project purpose; - installation; - Playwright
setup; - usage; - supported sites; - output schema; - screenshots if
useful; - known limitations; - ethical/operational constraints; - Yahoo
findings; - MSN findings.

------------------------------------------------------------------------

## Phase 11 - Supabase Database Integration & Staging

### Step 27 - Supabase Compatibility & Staging Layer

Implement `src/integrations/supabase/` compatibility and staging layer:
- `SupabaseArticleRow` and `SupabaseCommentRow` row models matching Supabase table schemas.
- `SupabaseMapper` converting collector Article/Comment objects into Supabase rows.
- Two-pass comment mapping with article-local parent resolution and structural parent fallback.
- Continuous globally unique negative integer comment staging IDs across the entire dataset.
- Article-scoped duplicate source comment ID collision detection.
- SHA-256 content hashing (`compute_content_hash()`).
- Omission rules for database defaults (`created_at`, `is_relevant`) vs nullable AI fields (`processing_*`).
- `SupabaseValidator` enforcing unique indexes (`articles_url_unique_idx`, `articles_content_hash_unique_idx`).
- `SupabaseCSVExporter` writing `articles_supabase.csv` and `comments_supabase.csv`.

Acceptance:
- Unit tests pass with zero network calls or live database access.
- Local mapping preserves rich collector objects while creating Supabase-compatible staging rows.

------------------------------------------------------------------------

### Step 28 - Supabase Preview & Export UI

Integrated the Supabase staging layer into the desktop application GUI (`src/gui/app.py` & `src/gui/supabase_preview.py`):
- Tab 4: "Supabase Articles Staging" Treeview table showing all 14 schema columns (`id`, `title`, `content`, `source`, `created_at`, `url`, `author`, `published_date`, `content_hash`, `clean_content`, `processing_status`, `processing_note`, `processed_at`, `is_relevant`) with vertical/horizontal scrolling and full un-truncated text detail panel.
- Tab 5: "Supabase Comments Staging" Treeview table showing all 5 schema columns (`id`, `article_id`, `text`, `created_at`, `parent_comment_id`) with vertical/horizontal scrolling and full un-truncated text detail panel.
- Validation Summary Panel and "Export Supabase CSVs..." button gated by staging validation status (disabled on errors/empty, enabled on valid/warnings).
- Thread-safe worker staging dataset generation (`SupabaseMapper.build_staging_dataset()`).
- Additive isolation: staging errors or export failures do not affect standard collection, summary, or JSON/CSV exports.
- Custom output directory file dialog prompt for export.
- Automatic state reset on new collection run.

Acceptance:
- Unit and integration tests pass with zero live database or network calls (`tests/test_gui_supabase_preview.py`).

------------------------------------------------------------------------

### Step 29 - Direct Supabase Upload (Future Step)

Implement dry-run validation and optional PostgREST/Supabase REST upload using project credentials.

------------------------------------------------------------------------

### Step 30 - Supabase Integration Verification (Future Step)

Verify end-to-end integration using mock/fake PostgREST test responses. If a real database smoke test is explicitly opted-in by configuration, execute a minimal smoke test (1 article, 1 top-level comment, 1 reply) against the shared database without table-wide deletions.

------------------------------------------------------------------------

## Future Backlog - Do Not Build Yet

Potential later work: - additional news-site adapters; - scheduler; - API/service layer; - NLP/sentiment analysis; - source health monitoring; - plugin-based adapter registration; - integration with the larger multi-agent AI-in-Education system (Note: Supabase database staging and upload is active in Phase 11 / Steps 27–30).

Do not add these until the Yahoo/MSN prototype is validated.

## Immediate Starting Point

After placing `AGENTS.md`, `PLAN.md`, and `BUILD_STEPS.md` in the
project root:

1.  Open the folder in Antigravity.

2.  Ask the coding agent to read all three files.

3.  Tell it:

    Read AGENTS.md, PLAN.md, and BUILD_STEPS.md. Follow their
    requirements. Begin with Step 1 only. Do not proceed to Step 2 until
    Step 1 has been completed and verified.

This keeps implementation controlled and makes debugging easier.
