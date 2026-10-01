# PLAN.md

## Adaptive News Article and Comment Collector

## 1. Project Goal

Create a local desktop application that can collect publicly accessible
news articles and associated public comments, when comments are
available, from supported news aggregators and news platforms.

Initial supported targets: 1. Yahoo News 2. MSN

Initial research topic: - AI in Education

The collection engine must remain topic-independent.

## 2. Research Motivation

The application supports an engineering-design research project that
needs: - a small reproducible sample of news articles; - comments
associated with those articles when available; - metadata describing the
source and publication; - evidence about which websites permit practical
article/comment collection; - documentation of technical limitations for
later development.

A major research question is not simply "Can comments be scraped?" but:
**How can the system reliably distinguish an article with no comments
from an article whose comments exist but were not accessible or
extractable?**

## 3. Success Criteria

A successful prototype can: - accept a Yahoo or MSN article URL; -
identify the source automatically; - load the public page; - extract
available article metadata; - extract the article body; - determine a
meaningful comment status; - collect public comments when technically
accessible; - preserve article/comment relationships; - export
normalized JSON and CSV; - explain extraction failures; - process a
small batch of URLs without manual code changes.

## 4. Non-Goals for the Initial Prototype

Do not initially implement: - paywall bypassing; - login/account
automation; - CAPTCHA solving; - anti-bot evasion; - VPN/proxy
rotation; - unrestricted crawling of entire websites; -
large-scale/high-frequency collection; - AI sentiment analysis; -
database infrastructure; - cloud deployment; - a complex multi-agent
architecture.

These were Non-Goals for the initial prototype (Steps 1–26). Following prototype completion, Supabase compatibility and database integration was promoted into the active post-prototype roadmap starting at Step 27.

## 5. High-Level Architecture

    +---------------------------+
    | Desktop Application / CLI |
    +-------------+-------------+
                  |
                  v
    +---------------------------+
    | Input & Validation Layer  |
    +-------------+-------------+
                  |
                  v
    +---------------------------+
    | Source Router             |
    +-------------+-------------+
                  |
          +-------+-------+
          |               |
          v               v
    +-----------+     +-----------+
    | Yahoo     |     | MSN       |
    | Adapter   |     | Adapter   |
    +-----+-----+     +-----+-----+
          |                 |
          +--------+--------+
                   |
                   v
    +---------------------------+
    | Normalization / Models    |
    +-------------+-------------+
                  |
                  v
    +---------------------------+
    | Validation & Diagnostics  |
    +-------------+-------------+
                  |
          +-------+-------+
          |               |
          v               v
    +-----------+   +-------------------------------+
    | Standard  |   | Supabase Staging Layer        |
    | JSON/CSV  |   | (src/integrations/supabase/)  |
    | Export    |   +---------------+---------------+
    +-----------+                   |
                                    v
                    +-------------------------------+
                    | Staging Preview / CSV Export  |
                    | & Direct Supabase Upload      |
                    +-------------------------------+

## 6. Proposed Project Structure

    news-article-comment-collector/
    |
    |-- AGENTS.md
    |-- PLAN.md
    |-- BUILD_STEPS.md
    |-- README.md
    |-- requirements.txt
    |-- .gitignore
    |
    |-- src/
    |   |-- main.py
    |   |-- app.py
    |   |-- config.py
    |   |
    |   |-- models/
    |   |   |-- article.py
    |   |   `-- comment.py
    |   |
    |   |-- collectors/
    |   |   |-- base.py
    |   |   |-- router.py
    |   |   |-- yahoo.py
    |   |   `-- msn.py
    |   |
    |   |-- extraction/
    |   |   |-- metadata.py
    |   |   |-- article_text.py
    |   |   `-- comments.py
    |   |
    |   |-- browser/
    |   |   `-- manager.py
    |   |
    |   |-- export/
    |   |   |-- json_exporter.py
    |   |   `-- csv_exporter.py
    |   |
    |   |-- integrations/
    |   |   `-- supabase/
    |   |       |-- models.py
    |   |       |-- mapper.py
    |   |       |-- validation.py
    |   |       `-- exporter.py
    |   |
    |   `-- utils/
    |       |-- logging.py
    |       `-- urls.py
    |
    |-- data/
    |   |-- input/
    |   |   `-- urls.txt
    |   |-- output/
    |   `-- diagnostics/
    |
    `-- tests/
        |-- fixtures/
        |-- test_router.py
        |-- test_models.py
        `-- test_exports.py

The exact structure may evolve, but adapters and normalized models must
remain separated.

## 7. Collection Pipeline

### Stage A: Input

Support: - single article URL; - multiple URLs from a text file; -
later: topic/search-assisted discovery.

Validate URLs before opening them.

### Stage B: Source Detection

The router recognizes domains and selects the proper adapter.

Examples: - Yahoo domains -\> Yahoo adapter - MSN domains -\> MSN
adapter - unknown domain -\> `UNSUPPORTED`

### Stage C: Page Acquisition

Attempt normal page retrieval.

Use Playwright when: - content is JavaScript rendered; - article fields
are absent from initial HTML; - comments require legitimate interaction.

Record loading failures rather than hiding them.

### Stage D: Article Extraction

Try, in order: 1. JSON-LD/structured data; 2. OpenGraph/meta tags; 3.
semantic article HTML; 4. source-specific selectors; 5. rendered DOM.

Normalize results into the Article model.

### Stage E: Comment Detection

Determine whether the page currently exposes a public comment facility.

Look for: - visible comment controls; - comment containers; - comment
counts; - embedded frames; - rendered public comment data; - legitimate
"View comments" / "Load more" interaction.

Do not equate inability to extract with zero comments.

### Stage F: Comment Collection

When public comments are accessible: - collect top-level comments; -
collect replies where feasible; - preserve parent/child relationships; -
collect only useful public metadata; - deduplicate records; - stop
according to configurable sample limits.

The initial research mode should allow a small limit such as 25-100
comments per article.

### Stage G: Validation

Check: - required URL/title fields; - empty article body; - duplicate
comments; - impossible counts; - malformed timestamps; - mismatch
between reported and collected comment counts.

### Stage H: Export

Produce: - one JSON result per run or article; - `articles.csv`; -
`comments.csv`; - diagnostic log.

## 8. Adaptation Strategy

Each adapter exposes a common interface conceptually similar to:

    supports(url)
    load(url)
    extract_article()
    detect_comments()
    extract_comments(limit)
    get_diagnostics()

If Yahoo changes its HTML, only the Yahoo adapter should normally
require changes.

Extraction should use fallbacks rather than a single CSS selector.

Example:

    JSON-LD title
         |
      missing?
         v
    OpenGraph title
         |
      missing?
         v
    semantic H1
         |
      missing?
         v
    Yahoo-specific selector
         |
      missing?
         v
    report field failure

## 9. Yahoo Strategy

Yahoo is the first implementation target.

Phase 1 should establish: - which Yahoo URL forms are supported; - where
title/author/date/publisher/body appear; - whether article data exists
in JSON-LD; - how live pages indicate comment availability; - whether
comments are in the DOM, frame, or dynamically requested; - whether
comment visibility varies by article/region/session.

Do not assume indexed "View comments" text means comments are currently
available.

Save diagnostic evidence when comment detection is ambiguous.

## 10. MSN Strategy

After Yahoo works: - implement MSN as a separate adapter; - reuse the
normalized Article/Comment models; - document differences in
syndication, article markup, and comments; - verify whether comments are
public and technically available.

Do not copy Yahoo selectors into MSN logic.

## 11. Desktop Application

Only after the collection engine is reliable, add a simple GUI.

Suggested screens/areas: - URL input - URL list import - topic field -
source selection - maximum comments per article - Start Collection
button - progress/status display - article result table - comment
status/count - error/diagnostic display - Export JSON - Export CSV -
Open Output Folder

The UI must not contain scraping logic; it calls the collection engine.

## 12. Topic-Assisted Collection

Later, support a topic such as `AI in Education`.

Prefer a transparent discovery workflow: 1. user enters topic; 2.
application obtains candidate article URLs through an approved
search/discovery method; 3. user can review candidates; 4. collector
processes selected URLs.

Keep discovery separate from article extraction so either component can
change independently.

## 13. Data Output Example

    {
      "platform": "Yahoo News",
      "requested_url": "...",
      "canonical_url": "...",
      "original_publisher": "...",
      "title": "...",
      "author": "...",
      "publication_datetime": "...",
      "article_text": "...",
      "retrieved_at": "...",
      "comments_status": "AVAILABLE",
      "comment_count_reported": 42,
      "comments_collected": 25,
      "comments": [
        {
          "comment_id": "...",
          "parent_comment_id": null,
          "author_display_name": "...",
          "comment_text": "...",
          "published_datetime": "...",
          "reactions": 4,
          "reply_count": 2,
          "depth": 0
        }
      ],
      "diagnostic_notes": []
    }

## 14. Research Logging

For sponsor documentation, retain a run summary such as:

    URL: ...
    Platform: Yahoo News
    Article extraction: SUCCESS
    Comments status: NOT_LOADED
    Reported comments: unknown
    Collected comments: 0
    Article method: JSON-LD + rendered DOM
    Comment method: visible-control detection
    Notes: No live comment container appeared after page load.

This turns failed collection attempts into useful engineering evidence.

## 15. Ethical / Operational Constraints

-   Use public pages.
-   Use conservative collection rates.
-   Do not defeat access controls.
-   Do not bypass subscriptions.
-   Do not automate personal accounts.
-   Do not collect unnecessary personal information.
-   Store only data necessary for the research objective.
-   Preserve URLs/timestamps for traceability.
-   Review site terms and institutional requirements before scaling
    collection.

## 16. Future Extensions

After Yahoo and MSN: - additional adapters; - scheduler; - article discovery APIs; - source health checks; - configurable collection policies; - NLP/sentiment/topic analysis; - integration into the larger AI-in-Education multi-agent system.

*(Note: Supabase database staging and upload integration was promoted into active development under Phase 11 / Steps 27–30).*
