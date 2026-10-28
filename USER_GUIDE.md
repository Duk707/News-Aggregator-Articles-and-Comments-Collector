# User Guide: Adaptive News Article and Comment Collector

Welcome to the **Adaptive News Article and Comment Collector** user manual. This guide provides comprehensive operational instructions for researchers, students, and end-users running the application either as a standalone Windows executable or from Python source code.

---

## Table of Contents

1. [Application Overview](#application-overview)
2. [Supported Sources & Scope](#supported-sources--scope)
3. [Launching the Application](#launching-the-application)
   - [Option A: Standalone Windows Executable](#option-a-standalone-windows-executable)
   - [Option B: Running from Python Source](#option-b-running-from-python-source)
4. [Main Interface Layout](#main-interface-layout)
5. [Direct URL Collection Mode](#direct-url-collection-mode)
6. [Candidate Discovery Mode](#candidate-discovery-mode)
   - [Search Parameters & Quotas](#search-parameters--quotas)
   - [Keyword Filtering Modes (ALL vs. ANY)](#keyword-filtering-modes-all-vs-any)
   - [Supabase Read-Only Duplicate Checking](#supabase-read-only-duplicate-checking)
   - [Candidate Discovery Behavior & Pagination](#candidate-discovery-behavior--pagination)
   - [Observed Publication Date Range Reporting](#observed-publication-date-range-reporting)
   - [Reviewing & Transferring Candidates](#reviewing--transferring-candidates)
7. [Collection Parameters & Execution Controls](#collection-parameters--execution-controls)
8. [Understanding Comment Statuses](#understanding-comment-statuses)
9. [Exporting Datasets & Supabase Integration](#exporting-datasets--supabase-integration)
   - [Standard Exports (JSON & CSV)](#1-standard-exports-json--csv)
   - [Supabase Staging Preview & CSV Export](#2-supabase-staging-preview--csv-export)
   - [Direct Supabase Database Upload](#3-direct-supabase-database-upload)
10. [Diagnostics & Troubleshooting](#diagnostics--troubleshooting)
11. [Documentation Links](#documentation-links)

---

## Application Overview

The application is a desktop research tool designed to discover, extract, and normalize public news articles and user comments from supported news aggregation websites: **Yahoo News** and **MSN**.

Key capabilities include:
- Interactive discovery of news articles by topic or keywords using Bing News RSS.
- Configurable per-source candidate quotas (Yahoo and MSN) with conditional pagination.
- Advanced keyword filtering with `ALL` (default) and `ANY` matching modes.
- Integrated read-only duplicate checking against Supabase to avoid collecting previously indexed articles.
- Extraction of article titles, authors, publication dates, and cleaned body text (free of advertisements and site boilerplate).
- Automated extraction of top-level user comments and nested reply chains.
- Transparent reporting of comment availability and diagnostic reasons when comments cannot be collected.
- Exporting collected datasets into JSON (nested format), relational CSV files (`articles.csv`, `comments.csv`), and Supabase staging CSV files (`articles_supabase.csv`, `comments_supabase.csv`).
- Direct, authenticated upload into Supabase database tables (`public.articles` and `public.comments`) with read-only dry run verification.

---

## Supported Sources & Scope

- **Primary Active Sources**:
  - **Yahoo News** (`news.yahoo.com`, `yahoo.com`)
  - **MSN** (`msn.com`)
  These are the primary, actively tested, and user-facing sources supported in both Direct URL Collection and Candidate Discovery.
- **Internal / Extension Adapters**:
  The repository includes 8 specialized blog and civic adapters (TESL Ontario, HEPI, EngagementHQ, Cult of Pedagogy, Spencer Education, Wonkhe, Granicus Ideas, Legistar). These adapters are internal backend implementations tested strictly with offline fixtures; they are not part of the active user-facing workflow and do not appear as selectable source options in Candidate Discovery.

---

## Launching the Application

### Option A: Standalone Windows Executable

The standalone Windows executable package (`NewsArticleCollector.exe`, ~334 MB) bundles a Python runtime and Playwright Chromium browser binaries (both standard Chromium and Chromium Headless Shell). No Python installation, Git commands, or separate Playwright setup is required to run the packaged application.

- **Local Working Build**: In this repository workspace, the verified executable is located at `dist-new/NewsArticleCollector.exe`.
- **GitHub Releases (When Published)**: When an official release asset is published to GitHub Releases, users can download `NewsArticleCollector.exe` directly from the project's Releases page without compiling from source.

#### Running the Executable
1. Locate `NewsArticleCollector.exe` (in `dist-new/` from a local build, or downloaded from a published GitHub Release).
2. Place `NewsArticleCollector.exe` in any normal writable folder on your computer.
3. Double-click `NewsArticleCollector.exe` to launch the graphical interface directly.

#### Handling the Windows SmartScreen Warning
Because this research prototype application is not signed with an expensive commercial code-signing certificate, Windows SmartScreen may present a prompt stating *"Windows protected your PC"* or *"Unknown Publisher"*.

To proceed when using a verified executable obtained from the official project repository or built locally:
1. Click the **"More info"** link on the SmartScreen dialog.
2. Click the **"Run anyway"** button.
3. The application will launch normally.

---

### Option B: Running from Python Source

If you prefer to run or modify the application using Python source code:

#### Prerequisites
- Validated on Windows 10/11 x64 (Python source code uses cross-platform Python libraries)
- Python 3.11+ installed

#### Setup Steps
1. Open a terminal or PowerShell prompt and clone the repository:
   ```powershell
   git clone https://github.com/Duk707/News-Aggregator-Articles-and-Comments-Collector.git
   cd News-Aggregator-Articles-and-Comments-Collector
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Install required dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Install the required Playwright Chromium browser driver:
   ```powershell
   playwright install chromium
   ```
5. Launch the desktop GUI:
   ```powershell
   python main.py
   ```

---

## Main Interface Layout

The main desktop window is organized into 4 vertical sections:

1. **1. Article URLs Input Panel**:
   - Multiline text entry area for direct article URL input.
   - **"Discover Candidates..."** button to open the automated discovery dialog.
   - **"Load from File..."** and **"Clear"** helper buttons.
2. **2. Collection Parameters & Operational Controls Panel**:
   - **Inter-Article Delay (sec)** (default: `2.0`): Pause duration between consecutive article network requests to ensure polite server interaction.
   - **Max Articles (limit)** (default: `50`): Maximum number of input articles to process during a single collection run.
   - **Max Comments / Article** (default: `50`): Maximum public comments to extract per article. Set to `0` to skip comment collection and extract article text only.
   - **Navigation Timeout (sec)** (default: `30`): Network timeout threshold for browser page loading.
   - **Topic / Research Label** (optional): Optional research label (e.g. `AI in Education`) attached to collected article metadata.
   - **Operational Controls**: **"Start Collection"** button, live Status label, and progress bar.
3. **3. Progress Logs & Collection Summary Panel**:
   - Multi-tab display containing:
     - **Tab 1: Execution Progress Log**: Real-time logging of article downloads, extraction events, and status updates.
     - **Tab 2: Research Article Results**: Interactive table of extracted articles with a resizable **Selected Article Inspection Panel**.
     - **Tab 3: Collection Run Summary**: Aggregate metrics summary of the completed run.
     - **Tab 4: Supabase Articles Staging**: Interactive table showing all 14 Supabase `public.articles` schema columns with full un-truncated text detail panel.
     - **Tab 5: Supabase Comments Staging**: Interactive table showing all 5 Supabase `public.comments` schema columns with full un-truncated text detail panel.
4. **4. Generated Dataset Outputs Panel**:
   - Displays default output paths (`data/output/articles.json`, `data/output/articles.csv`, `data/output/comments.csv`).
   - Displays real-time **Supabase Staging Status** indicator.
   - **"Open Output Folder"**: Opens the local output directory in Windows Explorer.
   - **"Export Supabase CSVs..."**: Exports validated `articles_supabase.csv` and `comments_supabase.csv` to a chosen directory.
   - **"Upload to Supabase..."**: Opens the modal upload dialog for pre-upload dry runs and direct database insertion.

---

## Direct URL Collection Mode

Direct URL mode allows you to collect specific Yahoo News or MSN articles by providing their URLs directly.

1. Locate **Section 1 (Article URLs Input)** on the main window.
2. Paste one or more news article URLs into the text entry area (one URL per line).
   - Supported URL formats include:
     - `https://news.yahoo.com/...`
     - `https://www.yahoo.com/news/...`
     - `https://www.msn.com/en-us/news/...`
3. Configure your desired collection options in **Section 2** (e.g. adjust *Max Comments / Article* or *Inter-Article Delay*).
4. Click **"Start Collection"**.

---

## Candidate Discovery Mode

Candidate Discovery mode discovers relevant Yahoo News and MSN articles automatically by topic or query phrase (such as `AI in Education`).

### Search Parameters & Quotas

Click **"Discover Candidates..."** in Section 1 to open the **Candidate Article Discovery & Preview** modal dialog:

- **Discovery Search Query (Optional)**: Enter your topic phrase (e.g., `AI in Education`). If left blank, Include Keywords will be used.
- **Sources & Independent Targets**:
  - **Yahoo News**: Checkbox and dedicated **Target** entry (default: `50`).
  - **MSN**: Checkbox and dedicated **Target** entry (default: `50`).
  Each source paginates independently until its specific target quota is satisfied or new results are exhausted.
- **Legacy Combined Max**:
  - Check this box to switch from independent source quotas to legacy combined maximum mode (default: `20` candidates shared across both platforms).

### Keyword Filtering Modes (ALL vs. ANY)

- **Include Keywords**: Comma-separated keywords that must appear in candidate headlines or summary snippets.
  - **Mode: ALL (Default)**: A candidate headline or snippet must match *all* specified include keywords (e.g., `AI, education` requires both terms).
  - **Mode: ANY**: A candidate headline or snippet must match at least *one* of the specified keywords. If the Search Query field is left blank in ANY mode, the discovery engine queries each keyword individually and aggregates results.
- **Exclude Keywords**: Comma-separated forbidden keywords. Any candidate matching an exclude keyword is omitted.

### Supabase Read-Only Duplicate Checking

- **"Check existing URLs in Supabase (read-only)"**:
  - When enabled, candidate URLs are checked in real time against existing records in your Supabase database before being presented in the preview table.
  - Excluded duplicates are tracked in real time, and the candidate table displays an active **DB Status** column:
    - **`New`**: URL was verified against Supabase and does not exist in the database.
    - **`Unverified`**: URL has not been checked against Supabase (e.g., if duplicate checking is disabled or credentials are not configured).
  - This check is strictly read-only and performs zero write operations.

### Candidate Discovery Behavior & Pagination

Candidate Discovery uses Bing News RSS as its underlying search index:
- **Keyset & Offset Pagination**: RSS pages are queried incrementally (`first=1`, `first=11`, `first=21`, ...) up to 10 pages per source.
- **Per-Source Early Stopping**: If an RSS offset query returns 0 new unique candidates for a source, the discovery engine terminates pagination for that source immediately to prevent redundant requests.
- **Source Balancing**: Candidate pools from enabled sources are merged using balanced round-robin selection so both platforms are fairly represented.
- **Tracking Parameter Removal**: Analytics and tracking query parameters (e.g., `utm_source`, `gclid`, `ncid`) are automatically stripped from candidate links.

### Observed Publication Date Range Reporting

Candidate Discovery automatically parses and normalizes publication timestamps provided in Bing News RSS item records.
- Once discovery completes, the dialog status bar displays the observed publication date range of the result set (for example: *"Status: Discovered 20 candidate article(s). Available dates in this search: 2026-10-01 to 2026-10-28."*).
- Note: External news RSS providers do not support reliable historical date range querying; this date range represents informational feedback about the observed result set.

### Reviewing & Transferring Candidates

1. Click **"Discover Candidates"** inside the dialog. The live **Discovery Diagnostics Report Panel** displays real-time pagination logs and duplicate check results.
2. Discovered candidates populate the preview table with columns: `Select`, `Platform`, `DB Status`, `Headline Title`, `Publication Date`, `Domain`, and `Validated Article URL`.
3. Select specific candidate check boxes or click **"Select All"** / **"Deselect All"**.
4. Click **"Import Selected Candidates to URL Input"** to transfer selected candidate URLs into Section 1 on the main window.

---

## Collection Parameters & Execution Controls

In **Section 2 (Collection Parameters & Operational Controls)**, adjust settings before starting:

- **Inter-Article Delay (sec)**: Sets request delay between articles (e.g. 2.0s).
- **Max Articles (limit)**: Maximum number of articles to process in the run.
- **Max Comments / Article**: Sets comment collection depth per article (e.g., 50, 100). Set to `0` to extract article text only.
- **Navigation Timeout (sec)**: Browser page navigation timeout threshold (e.g. 30s).
- **Topic / Research Label**: Optional research label attached to dataset records.

Click **"Start Collection"** to begin. The progress bar and status log will update in real time.

---

## Understanding Comment Statuses

The collector records an explicit comment status for every article to distinguish between true missing data, disabled features, and technical extraction failures:

| Status Code | Meaning & Cause |
| :--- | :--- |
| **`AVAILABLE`** | Public comments were successfully detected and extracted from the article page. |
| **`NONE_PRESENT`** | Comments are enabled on the article, but 0 public comments have been posted by users. |
| **`DISABLED`** | The publisher or platform explicitly turned off/disabled comments for this specific article. |
| **`LOGIN_REQUIRED`** | Comments are restricted and visible only to authenticated logged-in users. |
| **`NOT_LOADED`** | Page loading or script execution timed out before the comment section could be initialized. |
| **`BLOCKED`** | Access to the comment section or article was restricted by network security or bot protection. |
| **`UNSUPPORTED`** | The article URL format or platform domain is not supported for comment extraction. |
| **`UNKNOWN`** | Comment availability could not be conclusively determined from the page structure. |
| **`EXTRACTION_ERROR`** | Comments were detected on the page, but extraction failed due to a network error or DOM structural change. |

---

## Exporting Datasets & Supabase Integration

Once collection completes, dataset files are generated and available in several formats:

### 1. Standard Exports (JSON & CSV)

Saved automatically in `data/output/`:
- **`articles.json`**: Complete nested JSON file containing articles, full metadata, comment status metrics, and nested comment trees (with parent-child reply hierarchies).
- **`articles.csv`**: Tabular CSV spreadsheet containing article metadata, original requested URL, canonical publisher URL, publication date, cleaned body text, and comment metrics.
- **`comments.csv`**: Tabular CSV spreadsheet containing individual comment records (comment ID, author display name, comment text, timestamp, reactions, parent comment ID, reply depth). Each comment row contains an `article_url` foreign key linking it back to its parent article in `articles.csv`.

### 2. Supabase Staging Preview & CSV Export

- **Preview Tabs**: Switch to **Supabase Articles Staging** (Tab 4) or **Supabase Comments Staging** (Tab 5) to inspect the exact Supabase-shaped table rows before export. Selecting any table row opens its full un-truncated text in the bottom inspection panel.
- **Validation Status**: Section 4 displays real-time validation status (e.g. valid, warnings, or invalid error details).
- **Interactive Export**: Click **"Export Supabase CSVs..."** in Section 4 to open a folder dialog and export `articles_supabase.csv` (14 schema columns) and `comments_supabase.csv` (5 schema columns) to any chosen output directory.
- **Temporary Staging IDs**: The staging dataset uses continuous negative integer IDs (`-1`, `-2`, ...) to preserve relational parent-child hierarchies without conflicting with positive database autoincrement IDs.

### 3. Direct Supabase Database Upload

The **"Upload to Supabase..."** button in Section 4 provides a direct, authenticated upload path:
- **Connection & Credentials Dialog**: Enter your public Supabase Project URL (`https://<ref>.supabase.co`) and Publishable/Anon Key. Credentials can be optionally saved locally to `data/config/supabase_client_config.json` (git-ignored).
- **Zero Service Role Key & Memory-Only Auth**: Never uses or requests a `service_role` key. Optional user email/password authentication holds JWT access tokens strictly in memory without saving passwords or tokens to disk.
- **Read-Only Dry Run**: Click **"Run Read-Only Dry Run"** to verify connection, API key validity, active session role, read visibility, and Article conflict Cases A-D prior to any database write. The dry run makes zero write requests (0 POSTs) and explicitly displays: `Write permission (INSERT) unverified until live upload`.
- **Database Identity Translation**: Automatically converts temporary negative staging IDs (`-1`, `-101`) to real positive database IDs (`1001`, `5001`), omits missing `None` fields so database defaults (`now()`, `true`) apply, and inserts nested comment replies in topological order using real parent comment IDs.
- **Post-Upload Summary Report**: Upon completion, a summary modal displays total articles/comments inserted, linked, skipped, or failed, alongside detailed audit record logs.

---

## Diagnostics & Troubleshooting

### Diagnostic Snapshot Recording
When an article fails extraction or encounters an `EXTRACTION_ERROR`, diagnostic artifacts (including raw HTML dumps and error notes) are saved to `data/diagnostics/` relative to the application folder.

### Common Issues & Solutions

1. **GUI does not open when double-clicking EXE**:
   - Verify that the executable was downloaded completely from the official GitHub Releases page and that your local antivirus software is not blocking execution. Check Windows Task Manager to ensure no orphaned process instance is running.
2. **Comment status shows `NOT_LOADED` or `EXTRACTION_ERROR`**:
   - Check your internet connection. Some news articles dynamically load comment widgets via third-party JavaScript calls that may fail on slow or restricted connections.
3. **No candidates returned during discovery**:
   - Verify search terms and include keywords. If using `ALL` mode, candidates must match every included keyword. Try switching to `ANY` mode or broadening your discovery query phrase.
4. **Supabase Upload Dry Run Shows Partial Conflict (Case C)**:
   - Case C occurs when the requested article URL already exists in Supabase but the page content body has been updated since previous collection. The upload pipeline flags this conflict to prevent accidental data overwrites.

---

## Documentation Links

- 🏠 **[Project README](README.md)**: Overview, quick start, and system compatibility.
- 🛠️ **[Developer Guide](DEVELOPER.md)**: System architecture, adapter design, API specifications, PyInstaller build setup, and testing.
- 📋 **[Agent Rules](AGENTS.md)**: Engineering governance, approval gates, and source boundaries.
- 🗄️ **[Archived Project Plan](docs/archive/PLAN.md)**: Original prototype specification (Steps 1–26).
- 🗄️ **[Archived Build Steps](docs/archive/BUILD_STEPS.md)**: Historical implementation log (Steps 1–31).
