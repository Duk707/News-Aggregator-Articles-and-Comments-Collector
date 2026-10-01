# User Guide: Adaptive News Article and Comment Collector

Welcome to the **Adaptive News Article and Comment Collector** user manual. This guide provides comprehensive operational instructions for researchers, group members, and end-users running the application either as a standalone Windows executable or from Python source code.

---

## Table of Contents

1. [Application Overview](#application-overview)
2. [Launching the Application](#launching-the-application)
   - [Option A: Standalone Windows Executable](#option-a-standalone-windows-executable)
   - [Option B: Running from Python Source](#option-b-running-from-python-source)
3. [Main Interface Layout](#main-interface-layout)
4. [Direct URL Collection Mode](#direct-url-collection-mode)
5. [Candidate Discovery Mode](#candidate-discovery-mode)
   - [Search Parameters & Filters](#search-parameters--filters)
   - [Candidate Discovery Behavior & Pagination](#candidate-discovery-behavior--pagination)
   - [Observed Publication Date Range Reporting](#observed-publication-date-range-reporting)
   - [Reviewing & Transferring Candidates](#reviewing--transferring-candidates)
6. [Collection Options & Execution](#collection-options--execution)
7. [Understanding Comment Statuses](#understanding-comment-statuses)
8. [Exporting Datasets (JSON & CSV)](#exporting-datasets-json--csv)
9. [Diagnostics & Troubleshooting](#diagnostics--troubleshooting)
10. [Documentation Links](#documentation-links)

---

## Application Overview

The application is a desktop research tool designed to discover, extract, and normalize public news articles and user comments from supported news aggregation websites: **Yahoo News** and **MSN**.

Key capabilities include:
- Interactive discovery of news articles by topic or keywords.
- Filtering by required and forbidden keywords with match mode options.
- Extraction of article titles, authors, publication dates, and cleaned body text.
- Automated extraction of top-level user comments and nested reply chains.
- Transparent reporting of comment availability and diagnostic reasons when comments cannot be collected.
- Exporting collected datasets into JSON (nested format) and CSV (relational tables).

---

## Launching the Application

### Option A: Standalone Windows Executable

The standalone Windows executable package (`NewsArticleCollector.exe`) includes a bundled Python runtime and Playwright Chromium browser driver. No Python installation, Git commands, or separate Playwright setup is required for the packaged application. Pre-built executables are distributed through the project's **GitHub Releases** section.

1. Open the project's **GitHub Releases** page.
2. Download `NewsArticleCollector.exe` from the desired release asset list.
3. Place `NewsArticleCollector.exe` in any normal writable folder on your computer.
4. Double-click `NewsArticleCollector.exe` to launch the graphical interface directly.

#### Handling the Windows SmartScreen Warning
Because this prototype application is built for research and is not signed with a paid commercial code-signing certificate, Windows SmartScreen may present a blue prompt stating *"Windows protected your PC"* or *"Unknown Publisher"*.

To proceed when using a verified executable obtained from the official project repository:
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

1. **1. Article URLs Input**: Contains a multiline text entry box for direct URL input and the **"Discover Candidates..."** button.
2. **2. Collection & Extraction Options**: Contains the **"Collect Comments"** checkbox, **"Max Comments per Article"** limit entry, and the **"Start Collection"** button.
3. **3. Collection Progress & Results**: Contains a multi-tab view:
   - **Execution Progress Log**: Real-time log output and progress status.
   - **Research Article Results**: Interactive table of collected articles with a detailed **Selected Article Inspection Panel**.
   - **Collection Run Summary**: Metrics summary of the collection run.
   - **Supabase Articles Staging**: Interactive table showing all 14 Supabase `public.articles` schema columns with horizontal/vertical scrolling and an un-truncated row inspection panel.
   - **Supabase Comments Staging**: Interactive table showing all 5 Supabase `public.comments` schema columns with horizontal/vertical scrolling and an un-truncated row inspection panel.
4. **4. Generated Dataset Outputs**: Displays default output paths, Supabase staging validation status, **"Open Output Folder"**, and **"Export Supabase CSVs..."** buttons.

---

## Direct URL Collection Mode

Direct URL mode allows you to collect specific Yahoo News or MSN articles by providing their URLs directly.

1. Locate **Section 1 (Article URLs Input)** on the main window.
2. Paste one or more news article URLs into the text entry area (one URL per line).
   - Supported URL formats include:
     - `https://news.yahoo.com/...`
     - `https://www.yahoo.com/news/...`
     - `https://www.msn.com/en-us/news/...`
3. Configure your desired collection options in **Section 2** (see [Collection Options](#collection-options--execution)).
4. Click **"Start Collection"**.

---

## Candidate Discovery Mode

Candidate Discovery mode helps you discover relevant Yahoo News and MSN articles automatically by topic or query phrase (such as `AI in Education`).

### Search Parameters & Filters

Click **"Discover Candidates..."** in Section 1 to open the **Candidate Article Discovery** modal dialog:

- **Discovery Search Query (Optional)**: Enter your topic phrase (e.g., `AI in Education`). If left blank, Include Keywords will be used.
- **Sources**: Check **Yahoo News** and/or **MSN** to select which sources to search.
- **Max Candidates**: Set the maximum number of candidate records to retrieve (e.g., 10, 20, 30, 40+).
- **Include Keywords**: Specify comma-separated keywords that must appear in candidate headlines or snippets.
  - **Mode**:
    - **ANY (Default)**: Candidate headline or snippet must match at least one of the include keywords.
    - **ALL**: Candidate headline or snippet must match all specified include keywords.
- **Exclude Keywords**: Specify comma-separated forbidden keywords. Any candidate matching an exclude keyword will be omitted.

### Candidate Discovery Behavior & Pagination

Candidate Discovery uses Bing News RSS as its underlying search index and calculates pagination depth dynamically based on your requested `Max Candidates`:

$$\text{target\_pages\_per\_source} = \min\left(5, \max\left(2, \left\lceil \frac{\text{max\_candidates}}{8} \right\rceil\right)\right)$$

| Requested Max Candidates | RSS Pages per Source | RSS Offset Range (`first=`) |
| :--- | :--- | :--- |
| **10** | 2 pages | 1, 11 |
| **20** | 3 pages | 1, 11, 21 |
| **30** | 4 pages | 1, 11, 21, 31 |
| **40 or more** | 5 pages (maximum) | 1, 11, 21, 31, 41 |

#### Pagination & Merging Rules
- **Early Stopping**: If an RSS offset page returns 0 new unique candidates for a source, the discovery engine immediately stops querying additional pages for that source to prevent redundant requests.
- **Source Balancing**: Candidate pools from enabled sources are merged using balanced round-robin selection (e.g., 1 Yahoo, 1 MSN, 1 Yahoo, 1 MSN) so both platforms are represented fairly.
- **URL Tracking Parameter Removal**: Analytics and tracking parameters (e.g., `utm_source`, `gclid`, `ncid`) are automatically cleaned from candidate links.

### Observed Publication Date Range Reporting

Candidate Discovery automatically parses and normalizes publication timestamps provided in Bing News RSS item records.

- **Observed Date Reporting**: Once discovery completes, the dialog status bar automatically calculates and displays the observed publication date range for the discovered result set (for example: *"Status: Discovered 20 candidate article(s). Available dates in this search: 2026-09-20 to 2026-09-26."*).
- **Note on Search Filtering**: The GUI presents this observed date range as informational feedback regarding the current result set. It does not provide user-selectable start/end date search inputs because external news RSS providers do not support reliable historical date range querying.

### Reviewing & Transferring Candidates

1. Click **"Discover Candidates"** inside the dialog.
2. Discovered candidates will populate the preview table with check boxes (`[X]`), Platform, Headline Title, Publication Date, Domain, and Validated Article URL.
3. Select specific items or click **"Select All"**.
4. Click **"Import Selected Candidates to URL Input"** to transfer chosen candidate URLs into Section 1 on the main window.

---

## Collection Options & Execution

In **Section 2 (Collection & Extraction Options)**, adjust your settings:

- **Collect Comments**: Check this box to enable public comment extraction for supported articles. If unchecked, only article text and metadata will be collected.
- **Max Comments per Article**: Set the maximum number of public comments to collect per article (e.g., 50, 100, 500).

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

## Exporting Datasets (JSON & CSV)

Once collection completes, dataset files are automatically generated:

### 1. JSON Export (`articles.json`)
Exports a single structured JSON file containing all collected articles, complete metadata, comment status metrics, and nested comment trees (including parent-child reply relationships).

### 2. CSV Export (`articles.csv` & `comments.csv`)
Exports two relational CSV spreadsheets:
- **`articles.csv`**: Contains article-level records (title, author, publisher, publication date, cleaned body text, comment status, reported comment count, collected comment count).
- **`comments.csv`**: Contains individual comment records (comment ID, author name, comment text, timestamp, reaction counts, parent comment ID, depth level). Each comment row contains an `article_url` foreign key linking it back to its parent article in `articles.csv`.

### 3. Supabase Staging Preview & CSV Export (`articles_supabase.csv` & `comments_supabase.csv`)
Step 28 integrates user-facing Supabase staging preview tabs and export controls into the desktop application GUI:
- **Preview Tabs**: Switch to **Supabase Articles Staging** (Tab 4) or **Supabase Comments Staging** (Tab 5) to inspect the exact Supabase-shaped table rows before export. Selecting any table row opens its full un-truncated text in the bottom inspection panel.
- **Validation Status**: Section 4 displays real-time validation status (e.g. valid, warnings, or invalid error details).
- **Interactive Export**: Click **"Export Supabase CSVs..."** in Section 4 to open a folder dialog and export `articles_supabase.csv` (14 schema columns) and `comments_supabase.csv` (5 schema columns) to any chosen output directory.
- **Export Gating**: The export button is disabled when validation errors or an empty dataset are present, and enabled when the dataset is valid or contains warnings.

*Important Notes*:
- Because these Supabase CSV files use temporary negative staging IDs (`-1`, `-2`, ...) for relationship tracking, they are classified as staging/export files for relationship inspection and staging, not direct raw database imports.

Outputs are saved relative to the application working directory in `data/output/` (beside `NewsArticleCollector.exe` when running the executable). You can also click **"Export Datasets..."** in Section 4 to save copies to a custom folder.

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
   - Verify search terms and include keywords. Try broadening your discovery query phrase.

---

## Documentation Links

- 🏠 **[Project README](README.md)**: Overview and quick start.
- 🛠️ **[Developer Guide](DEVELOPER.md)**: System architecture, Yahoo/MSN comment API specifications, PyInstaller build setup, and unit testing.
