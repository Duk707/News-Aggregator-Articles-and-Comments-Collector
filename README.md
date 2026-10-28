# Adaptive News Article and Comment Collector

A local computer application designed to collect publicly accessible news articles and public user comments from supported news aggregation platforms (**Yahoo News** and **MSN**).

---

## Overview & Purpose

This research prototype supports an engineering design project focusing on **AI in Education** (while remaining fully topic-independent). It provides a reliable, transparent, adapter-driven collection pipeline that extracts public article text, metadata, and user comments without resorting to paywall bypasses, CAPTCHA solving, or stealth mechanisms.

### Key Capabilities

- **Desktop Graphical Interface**: Interactive Tkinter / TTK interface featuring resizable panels, execution progress logs, research inspection tables, and a 5-tab preview interface.
- **Direct URL Collection**: Enter individual or batch article URLs from Yahoo News and MSN.
- **Candidate Article Discovery**: Automated article discovery powered by Bing News RSS with independent per-source quotas (Yahoo and MSN, default 50 each), keyword filtering (`ALL` default and `ANY` modes), legacy combined max mode, and live diagnostics reporting.
- **Supabase Duplicate Verification**: Optional, read-only pre-collection verification against existing Supabase database records to exclude duplicate URLs and display candidate verification status (`New` vs. `Unverified`).
- **Clean Article Body Extraction**: Standardized extraction of article titles, authors, publication dates, canonical URLs, and cleaned body text free of ads and boilerplate.
- **Public Comment Extraction**: Extraction of top-level comments and nested reply chains from supported Yahoo News and MSN articles.
- **Granular Comment Status Classification**: Distinguishes between articles with no comments (`NONE_PRESENT`), disabled comments (`DISABLED`), accessible comments (`AVAILABLE`), and inaccessible comments (`LOGIN_REQUIRED`, `NOT_LOADED`, `BLOCKED`, `EXTRACTION_ERROR`).
- **Relational Data Exports**: Generates nested JSON (`articles.json`), relational CSV files (`articles.csv` and `comments.csv`), and Supabase staging CSV files (`articles_supabase.csv` and `comments_supabase.csv`).
- **Supabase Staging Preview & Upload**: Dedicated GUI preview tabs for inspecting Supabase table rows with un-truncated text inspection, read-only pre-upload dry run validation, and interactive database upload dialogs.
- **Diagnostic Logging**: Automated snapshot recording of HTML structures and extraction diagnostics in `data/diagnostics/`.

---

## Supported Sources & Scope

- **Primary Active Sources**:
  - **Yahoo News** (`news.yahoo.com`, `yahoo.com`)
  - **MSN** (`msn.com`)
  Yahoo News and MSN are the two primary, actively maintained, and live-tested sources in the application. They are the only sources selectable in the Candidate Discovery GUI.
- **Internal / Extension Adapters**:
  The repository contains 8 additional blog and civic adapters (TESL Ontario, HEPI, EngagementHQ, Cult of Pedagogy, Spencer Education, Wonkhe, Granicus Ideas, Legistar). These adapters represent internal backend modules tested strictly with offline fixtures; they are not part of the active user-facing collection workflow and do not appear as selectable sources in the Candidate Discovery GUI.

---

## System Compatibility

- **Standalone Executable**:
  - **Target Compatibility**: 64-bit Windows (Windows 10 / Windows 11 x64).
  - **Tested Environment**: Verified on **64-bit Windows 11**.
- **Python Source Code**:
  - **Version Requirement**: Python 3.11+.
  - **Tested Environment**: Verified on **Python 3.13** under 64-bit Windows 11 (source code uses cross-platform Python standard libraries and Playwright).

---

## Quick Start

### 1. Standalone Windows Executable (Recommended for Non-Developers)

The standalone executable package (`NewsArticleCollector.exe`, ~334 MB) bundles a Python runtime and Playwright Chromium browser binaries (both standard Chromium and Chromium Headless Shell). No Python installation, Git commands, or separate Playwright setup is required to run the packaged application.

- **Local Working Build**: The locally verified executable is located at `dist-new/NewsArticleCollector.exe`.
- **GitHub Releases (When Published)**: When an official release asset is published to the repository's GitHub Releases section, users can download `NewsArticleCollector.exe` directly without compiling from source.

#### Running the Executable
1. Locate `NewsArticleCollector.exe` (either in `dist-new/` from a local build or from a published GitHub Release).
2. Place `NewsArticleCollector.exe` in any normal writable folder on your computer.
3. Double-click `NewsArticleCollector.exe` to launch the application.

> **Note on File Outputs**: The standalone executable creates and manages its `data/` directories (`data/output/` and `data/diagnostics/`) relative to the folder where `NewsArticleCollector.exe` is placed.
>
> **Note on Windows SmartScreen**: If Windows displays an *"Unknown Publisher"* or *"Windows protected your PC"* prompt upon launch, click **"More info"** and select **"Run anyway"**. This prompt appears because prototype research binaries are not signed with a commercial certificate.

---

### 2. Running from Python Source Code

Requires Python 3.11+ installed.

```powershell
# 1. Clone the public repository and navigate into the folder
git clone https://github.com/Duk707/News-Aggregator-Articles-and-Comments-Collector.git
cd News-Aggregator-Articles-and-Comments-Collector

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install required dependencies
pip install -r requirements.txt

# 4. Install Playwright browser binaries
playwright install chromium

# 5. Launch the desktop GUI
python main.py
```

---

## Outputs Overview

Standard collection runs automatically generate datasets in `data/output/`:

- **`articles.json`**: Complete nested dataset containing articles, metadata, comment status metrics, and nested comment trees.
- **`articles.csv`**: Tabular dataset containing article metadata, URLs, publication dates, and summary metrics.
- **`comments.csv`**: Tabular dataset containing individual comments and replies, linked to parent articles via `article_url`.

*Supabase Staging & Export*: The application provides dedicated GUI tabs (Tabs 4 & 5) and the **"Export Supabase CSVs..."** button, enabling previewing and custom-folder export of `articles_supabase.csv` and `comments_supabase.csv` using temporary staging IDs. The **"Upload to Supabase..."** button enables pre-upload dry run checks and direct authenticated upload.

---

## Documentation Links

For detailed operational instructions, architectural specifications, and project rules, refer to:

- 📖 **[User Guide](USER_GUIDE.md)**: Comprehensive manual covering GUI navigation, Candidate Discovery parameters, export options, and troubleshooting.
- 🛠️ **[Developer Guide](DEVELOPER.md)**: In-depth technical documentation covering system architecture, adapter design, API specifications, PyInstaller build instructions, and testing.
- 📋 **[Agent Rules](AGENTS.md)**: Engineering governance, source scope boundaries, modular collection principles, and two-gate approval workflows.
- 🗄️ **[Archived Project Plan](docs/archive/PLAN.md)**: Historical architectural specification and initial development plan (Steps 1–26).
- 🗄️ **[Archived Build Steps](docs/archive/BUILD_STEPS.md)**: Historical step-by-step implementation and verification log (Steps 1–31).

---

## Repository Structure

```text
.
├── src/                       # Application source code
│   ├── browser/               # Browser automation manager (Playwright)
│   ├── collectors/            # SourceRouter, base adapter, Yahoo, MSN, and extension adapters
│   ├── discovery/             # Candidate Discovery engine (Bing News RSS parser & Legistar API)
│   ├── export/                # JSON and CSV export generators
│   ├── extraction/            # Article text, comment, metadata, and WordPress extractors
│   ├── gui/                   # Desktop graphical user interface (Tkinter / TTK)
│   ├── integrations/          # External integrations (Supabase compatibility & staging layer)
│   │   └── supabase/          # Supabase models, mapper, validator, client, and uploader
│   ├── models/                # Dataclass models (Article, Comment, CandidateArticle, etc.)
│   └── utils/                 # URL validation and helper functions
├── tests/                     # Automated unit and integration test suite (with fixtures)
├── docs/                      # Project documentation archives
│   └── archive/               # Historical specifications and step-by-step implementation logs
│       ├── PLAN.md            # Archived prototype design plan (Steps 1–26)
│       └── BUILD_STEPS.md     # Archived historical implementation log (Steps 1–31)
├── data/                      # Data folder templates (.gitkeep files)
│   ├── input/                 # Input URL batch file directory
│   ├── output/                # Exported JSON and CSV datasets directory
│   └── diagnostics/           # Extraction diagnostics and HTML snapshots directory
├── main.py                    # Application launch entry point
├── NewsArticleCollector.spec  # PyInstaller packaging configuration
├── requirements.txt           # Python dependency requirements
├── pytest.ini                 # Pytest test suite configuration
├── .gitignore                 # Git ignore rules for environments, outputs, and scratch files
├── README.md                  # Project overview and quick start (this file)
├── USER_GUIDE.md              # End-user manual and operational guide
├── DEVELOPER.md               # Technical architecture and developer documentation
└── AGENTS.md                  # Engineering governance rules and approval gates
```

---

## Ethical Collection & Responsible Use Statement

This application is built for academic and research purposes. It exclusively collects publicly accessible news articles and public user comments available through standard site access. It does **not** bypass paywalls, solve CAPTCHAs, use proxy rotation, or bypass user authentication controls. Conservative request delays are enforced to respect source server bandwidth.
