# Adaptive News Article and Comment Collector

A local computer application designed to collect publicly accessible news articles and their public comments from supported news aggregation platforms (starting with Yahoo News and MSN).

## Overview & Purpose

This research prototype supports an engineering design project focusing on **AI in Education** (and topic-independent news analysis). It provides a reliable, transparent, and adapter-driven collection pipeline that collects public article content, metadata, and user comments without resorting to paywall bypasses, CAPTCHA solving, or stealth mechanisms.

### Key Capabilities

- **GUI Interface**: User-friendly desktop interface built with Tkinter / TTK.
- **Direct URL Collection**: Enter individual or batch news article URLs from Yahoo News and MSN.
- **Candidate Discovery**: Topic-based discovery powered by Bing News RSS with keyword filtering, observed date range reporting, and source-balanced candidate selection.
- **Full Article Extraction**: Standardized extraction of article titles, authors, publication dates, canonical URLs, and cleaned article text (free of site boilerplate).
- **Public Comment Extraction**: Automated extraction of top-level comments and nested replies from supported Yahoo News and MSN articles.
- **Rich Comment Status Classification**: Distinguishes between articles with no comments (`NONE_PRESENT`), disabled comments (`DISABLED`), available comments (`AVAILABLE`), and inaccessible comments (`LOGIN_REQUIRED`, `NOT_LOADED`, `BLOCKED`, `EXTRACTION_ERROR`).
- **Data Export & Direct Upload**: Export collected datasets into nested JSON files, standard CSV files (`articles.csv` and `comments.csv`), Supabase staging CSV files (`articles_supabase.csv` and `comments_supabase.csv`), or perform a direct upload into Supabase database tables (`public.articles` and `public.comments`).
- **Supabase Staging Preview & Upload**: GUI preview tabs for inspecting 14-column Supabase articles staging rows and 5-column Supabase comments staging rows with detail inspection panels, read-only pre-upload dry run verification, and interactive database upload dialogs (Implementation: **COMPLETE and MOCK-VERIFIED**; Live verification: **DEFERRED — awaiting Supabase project connection information and RLS verification**).
- **Diagnostic Logging**: Automated snapshot recording of HTML structures and extraction errors in `data/diagnostics/`.

---

## Supported Sources & System Compatibility

- **Supported Platforms**: Yahoo News (`news.yahoo.com`, `yahoo.com`) and MSN News (`msn.com`).
- **Validated Operating Systems**:
  - **Standalone Executable**: Validated for **64-bit Windows** (Windows 10/11 x64).
  - **Python Source Code**: Designed for **Python 3.11+** (validated on Windows; source code uses cross-platform Python libraries).

---

## Quick Start

### 1. Standalone Windows Executable (Recommended for Non-Developers)

No Python installation, Git commands, or separate Playwright setup is required to run the packaged application. Pre-built standalone executables are distributed through the project's **GitHub Releases** section.

1. Open the repository's **Releases** section on GitHub.
2. Download `NewsArticleCollector.exe` from the desired release asset list.
3. Place `NewsArticleCollector.exe` in any normal writable folder on your computer.
4. Double-click `NewsArticleCollector.exe` to launch the graphical interface directly.

> **Note on File Outputs**: The standalone executable creates and manages its `data/` directories (`data/output/` and `data/diagnostics/`) relative to the location of the `.exe` file.
>
> **Note on Windows SmartScreen**: If Windows displays an *"Unknown Publisher"* or *"Windows protected your PC"* prompt upon launch, verify that you downloaded the executable from the official project repository, then click **"More info"** and select **"Run anyway"**. This warning appears because the prototype executable is un-signed.

### 2. Running from Python Source Code

Requires Python 3.11+ installed.

```bash
# 1. Clone the public repository and navigate into the folder
git clone https://github.com/Duk707/News-Aggregator-Articles-and-Comments-Collector.git
cd News-Aggregator-Articles-and-Comments-Collector

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows

# 3. Install required dependencies
pip install -r requirements.txt

# 4. Install Playwright browser binaries
playwright install chromium

# 5. Launch the application
python main.py
```

---

## Outputs Overview

Standard collection runs automatically generate datasets in `data/output/`:

- **`articles.json`**: Complete nested dataset containing articles and their associated comment trees.
- **`articles.csv`**: Tabular dataset containing article metadata, URLs, publication dates, and summary metrics.
- **`comments.csv`**: Tabular dataset containing individual comments and replies, linked to parent articles via `article_url`.

*Note on Supabase Staging Preview & Exports*: Step 28 added interactive GUI preview tabs (Tabs 4 & 5) and the **"Export Supabase CSVs..."** button, enabling previewing and custom folder export of `articles_supabase.csv` and `comments_supabase.csv` (using temporary negative staging IDs for relationship tracking).

---

## Documentation Links

For detailed guides and technical specifications, refer to:

- 📖 **[User Guide](USER_GUIDE.md)**: Comprehensive manual covering GUI navigation, Candidate Discovery parameters, export options, and SmartScreen handling.
- 🛠️ **[Developer Guide](DEVELOPER.md)**: In-depth technical documentation covering system architecture, adapter design, candidate discovery formulas, Yahoo/MSN comment API specifications, PyInstaller build instructions, and testing.

---

## Repository Structure

```text
.
├── src/                       # Application source code
│   ├── browser/               # Browser automation manager (Playwright)
│   ├── collectors/            # SourceRouter, base adapter, Yahoo & MSN collection pipeline
│   ├── discovery/             # Candidate Discovery engine (Bing News RSS parser)
│   ├── export/                # JSON and CSV export generators
│   ├── extraction/            # Article text, comment, and metadata extraction routines
│   ├── gui/                   # Desktop graphical user interface (Tkinter / TTK)
│   ├── integrations/          # External integrations (Supabase compatibility & staging layer)
│   │   └── supabase/          # Supabase models, mapper, validator, and staging exporter
│   ├── models/                # Dataclass models (Article, Comment, CandidateArticle, etc.)
│   └── utils/                 # URL validation and helper functions
├── tests/                     # Automated unit and integration test suite (with fixtures)
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
└── DEVELOPER.md               # Technical architecture and developer documentation
```

---

## Ethical Collection & Responsible Use Statement

This application is built for academic and research purposes. It exclusively collects publicly accessible news articles and public user comments available through standard site access. It does **not** bypass paywalls, solve CAPTCHAs, use proxy rotation, or bypass user authentication controls. Conservative request delays are enforced to respect source server bandwidth.
