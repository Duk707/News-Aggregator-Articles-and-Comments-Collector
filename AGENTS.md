# AGENTS.md

## Project: Adaptive News Article and Comment Collector

### Purpose

Build a local computer application that collects publicly accessible
news articles and, when available, their public comments from supported
news/aggregation websites such as Yahoo News and MSN.

The immediate research topic is **AI in Education**, but the software
must be topic-independent so the user can later enter other search
terms, URLs, and sources.

This is a research prototype for an engineering design project.
Reliability, traceability, and transparent failure reporting are more
important than maximizing the number of collected records.

## Core Agent Rules

1.  Work incrementally. Follow `PLAN.md` and `BUILD_STEPS.md`.
2.  Complete and test one build step before starting the next.
2a. After completing and testing each build step, provide a comprehensive end-of-step walkthrough explaining:
    - Files created or modified
    - Purpose of each file
    - How the functionality works
    - Important code, functions, and classes
    - How the step connects to the overall program
    - Tests executed and verification results
    - Any limitations, edge cases, or issues
    - What the next step will add
2b. Mandatory Pre-Implementation Approval Gate for Remaining Steps (Steps 21–26):
    Steps 1–20 are completed. For all remaining build steps (Steps 21–26), follow a strict two-gate approval workflow:
    - **Gate 1 (Pre-Implementation Plan & Approval)**:
      1. Review `AGENTS.md`, `PLAN.md`, `BUILD_STEPS.md`, and the relevant existing implementation.
      2. Produce a concise implementation plan before making any implementation changes. The plan must identify:
         - files expected to be created or modified;
         - classes/functions/components expected to be added or changed;
         - how the work integrates with the existing architecture;
         - testing and verification strategy;
         - important design decisions, assumptions, and risks;
         - anything explicitly out of scope for that step.
      3. **STOP** and wait for explicit user approval of the implementation plan before making any code or configuration edits.
    - **Implementation & Testing**:
      4. Only after plan approval, implement that step.
      5. Run the appropriate tests and verification.
    - **Gate 2 (Post-Implementation Walkthrough & Approval)**:
      6. Provide the required end-of-step walkthrough (per Rule 2a).
      7. **STOP** and wait for explicit user approval before proceeding to the next build step.
3.  Do not invent selectors, endpoints, comments, metadata, or
    successful extraction results.
4.  Do not silently treat extraction failure as "no comments."
5.  Keep source-specific logic isolated from the shared collection
    pipeline.
6.  Prefer maintainable extraction strategies over brittle hard-coded
    selectors.
7.  Record why extraction failed when content cannot be collected.
8.  Preserve provenance for every collected article and comment.
9.  Do not bypass paywalls, authentication controls, CAPTCHAs, access
    controls, or anti-bot protections.
10. Collect only content that is publicly accessible through normal site
    access.
11. Respect applicable site terms, robots policies where relevant, rate
    limits, and reasonable request delays.
12. Do not implement VPN/proxy rotation, CAPTCHA solving, account
    automation, or stealth/evasion mechanisms in this prototype.
13. Never commit secrets, cookies, session tokens, credentials, or
    personal browser profiles.
14. Keep diagnostic artifacts separate from final datasets.
15. Before adding a dependency, explain why it is needed and update
    `requirements.txt`.

## Intended User Workflow

The application should eventually support: - Entering one or more
article URLs. - Entering a topic/search phrase such as
`AI in Education`. - Selecting one or more supported sources. -
Collecting article metadata and article text. - Detecting whether
comments are currently accessible. - Collecting public comments and
replies when supported. - Previewing results. - Exporting results to
JSON and CSV. - Viewing failures and extraction diagnostics.

## Architecture Principle: Adapter-Based Collection

Do NOT create one giant scraper with site-specific conditions scattered
throughout the code.

Use a shared interface with source adapters, for example:

    Collector Application
            |
       Source Router
       /          \
    YahooAdapter  MSNAdapter
       \          /
       Normalized Data
            |
       JSON / CSV

A source adapter is responsible for source-specific: - URL recognition -
page loading - article extraction - comment detection - comment
extraction - pagination / "load more" behavior - diagnostics

Shared code is responsible for: - data models - validation -
deduplication - normalization - logging - rate limiting - exports -
application UI

## Adaptiveness

"Adaptive" means the program can: 1. Detect which supported source owns
a URL. 2. Route the URL to the appropriate adapter. 3. Try multiple
legitimate extraction strategies in a defined order. 4. Detect
missing/changed page structures. 5. return explicit statuses rather than
fabricated data. 6. Add new websites through new adapters without
rewriting the application.

It does NOT mean automatically defeating website protections.

### Recommended extraction strategy order

For articles: 1. Structured metadata (`application/ld+json`, OpenGraph,
standard meta tags). 2. Semantic HTML (`article`, headings, time
elements). 3. Source-specific selectors. 4. Browser-rendered DOM when
JavaScript is required.

For comments: 1. Detect a visible public comments feature. 2. Inspect
rendered DOM/frames for publicly loaded comment data. 3. Use
documented/public endpoints only when appropriate and permitted. 4.
Interact with legitimate "View comments"/"Load more" controls when
needed. 5. If unavailable, return an explicit status and diagnostic
reason.

## Comment Status Model

Do not represent comments with only True/False.

Use statuses such as: - `AVAILABLE` - `NONE_PRESENT` - `DISABLED` -
`LOGIN_REQUIRED` - `NOT_LOADED` - `BLOCKED` - `UNSUPPORTED` -
`UNKNOWN` - `EXTRACTION_ERROR`

This distinction is essential to the research.

## Data Model

### Article

Capture when available: - `platform` - `source_adapter` -
`requested_url` - `canonical_url` - `original_publisher` - `title` -
`author` - `publication_datetime` - `updated_datetime` -
`article_text` - `language` - `topic/query` - `retrieved_at` -
`comments_status` - `comment_count_reported` - `comments_collected` -
`extraction_method` - `diagnostic_notes`

### Comment

Capture when publicly available: - `comment_id` - `article_url` -
`parent_comment_id` - `author_display_name` - `comment_text` -
`published_datetime` - `reactions` - `reply_count` - `depth` -
`retrieved_at`

Do not collect unnecessary personal information.

## Technical Direction

Preferred initial stack: - Python 3.11+ - Playwright for
JavaScript-rendered pages - BeautifulSoup4 for HTML parsing - `requests`
only where ordinary HTTP retrieval is sufficient - Python dataclasses or
Pydantic for normalized models - standard `logging` - JSON and CSV
exports - pytest for tests

For the eventual desktop UI, prefer a simple Python UI such as
CustomTkinter/Tkinter unless the build reveals a better justified
option. Do not build the GUI before the collection engine works.

## Browser Automation Rules

-   Use a fresh, project-controlled browser context.
-   Do not import the user's normal browser cookies.
-   Use visible/headed browser mode during diagnostics when helpful.
-   Use explicit waits rather than arbitrary long sleeps where possible.
-   Apply conservative delays between article requests.
-   Stop or report clearly when the site presents CAPTCHA/access denial.
-   Save diagnostics only when useful and avoid retaining unnecessary
    user/session data.

## Output Requirements

JSON should preserve nested article/comment relationships.

CSV should normally be split into: - `articles.csv` - `comments.csv`

Use stable article identifiers so comments can be joined back to their
articles.

## Quality Requirements

Every extraction run must be able to answer: - Which URL was
requested? - Which source adapter handled it? - When was it retrieved? -
Did article extraction succeed? - Which fields were missing? - Were
comments available? - If comments were not collected, why? - How many
comments were reported? - How many were actually collected? - Which
extraction method was used?

## Testing

Tests should include: - source URL recognition - metadata
normalization - missing fields - articles without comments - comment
status distinctions - malformed URLs - duplicate URLs/comments - adapter
failure handling - export consistency

Do not make live Yahoo/MSN access the only test suite. Save small
sanitized fixtures where appropriate so parsers can be tested
deterministically.

## Scope Control

The initial milestone is NOT a universal news scraper.

Milestone 1: - Yahoo News adapter - single URL - article extraction -
comment detection diagnostics - JSON output

Milestone 2: - Yahoo public comment extraction if technically
available - multiple URLs - CSV export

Milestone 3: - MSN adapter - shared source router

Milestone 4: - simple desktop application - topic/search-assisted
workflow - batch collection

Only after these milestones should additional sources be considered.
