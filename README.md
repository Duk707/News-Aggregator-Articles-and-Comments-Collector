# Adaptive News Article and Comment Collector

A local computer application designed to collect publicly accessible news articles and their public comments from supported news aggregation platforms (starting with Yahoo News and MSN).

## Overview & Purpose

This research prototype supports an engineering design project focusing on **AI in Education** (and topic-independent news analysis). It provides a reliable, transparent, and adapter-driven collection pipeline that collects public article content, metadata, and user comments without resorting to paywall bypasses, CAPTCHA solving, or stealth mechanisms.

### Key Capabilities

- **GUI Interface**: User-friendly desktop interface built with CustomTkinter and Tkinter.
- **Direct URL Collection**: Enter individual or batch news article URLs from Yahoo News and MSN.
- **Candidate Discovery**: Topic-based discovery powered by Bing News RSS with keyword filtering, observed date range reporting, and source-balanced candidate selection.
- **Full Article Extraction**: Standardized extraction of article titles, authors, publication dates, canonical URLs, and cleaned article text (free of site boilerplate).
- **Public Comment Extraction**: Automated extraction of top-level comments and nested replies from supported Yahoo News and MSN articles.
- **Rich Comment Status Classification**: Distinguishes between articles with no comments (`NONE_PRESENT`), disabled comments (`DISABLED`), available comments (`AVAILABLE`), and inaccessible comments (`LOGIN_REQUIRED`, `NOT_LOADED`, `BLOCKED`, `EXTRACTION_ERROR`).
- **Data Export**: Export collected datasets into nested JSON files or tabular CSV files (`articles.csv` and `comments.csv`).
- **Diagnostic Logging**: Automated snapshot recording of HTML structures and extraction errors in `data/diagnostics/`.

---

## Supported Sources

- **Yahoo News** (`news.yahoo.com`, `yahoo.com`)
- **MSN News** (`msn.com`)

---

## Quick Start

### 1. Standalone Windows Executable (Recommended for Non-Developers)

No Python installation or command-line setup is required to run the pre-built executable. The single-file package includes a bundled Python runtime and Playwright Chromium driver.

1. Navigate to the `dist/` directory.
2. Double-click `NewsArticleCollector.exe`.
3. The graphical user interface will open directly.

> **Note on Windows SmartScreen**: If Windows displays an *"Unknown Publisher"* or *"Windows protected your PC"* prompt upon launch, click **"More info"** and then select **"Run anyway"**. This warning appears because the prototype executable is un-signed.

### 2. Running from Python Source Code

Requires Python installed on Windows, Linux, or macOS.

```bash
# 1. Clone or extract the repository
cd "New article and Comments Collector"

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

Collected datasets are automatically written to `data/output/`:

- **`articles.json`**: Complete nested dataset containing articles and their associated comment trees.
- **`articles.csv`**: Tabular dataset containing article metadata, URLs, publication dates, and summary metrics.
- **`comments.csv`**: Tabular dataset containing individual comments and replies, linked to parent articles via `article_url`.

---

## Documentation Links

For detailed guides and technical specifications, refer to:

- 📖 **[User Guide](USER_GUIDE.md)**: Comprehensive manual covering GUI navigation, Candidate Discovery parameters, export options, and SmartScreen handling.
- 🛠️ **[Developer Guide](DEVELOPER.md)**: In-depth technical documentation covering system architecture, adapter design, candidate discovery formulas, Yahoo/MSN comment API specifications, PyInstaller build instructions, and testing.

---

## Repository Structure

```text
.
├── dist/                      # Packaged standalone executable (NewsArticleCollector.exe)
├── src/                       # Application source code
│   ├── collectors/            # SourceRouter and collection pipeline orchestrator
│   ├── adapters/              # Platform adapters (YahooAdapter, MSNAdapter)
│   ├── discovery/             # Candidate Discovery engine (Bing News RSS parser)
│   ├── extraction/            # Article text and metadata extraction routines
│   ├── comments/              # Public comment extraction (Yahoo GraphQL & MSN REST)
│   ├── exporters/             # JSON and CSV export generators
│   ├── gui/                   # Desktop graphical user interface (CustomTkinter)
│   └── models/                # Dataclass models (Article, Comment, CandidateArticle)
├── tests/                     # Automated unit and integration test suite
├── data/                      # Persistent storage directory
│   ├── input/                 # Input URL batch files
│   ├── output/                # Exported JSON and CSV datasets
│   └── diagnostics/           # Extraction diagnostics and HTML snapshots
├── scratch/                   # Historical research, analysis, and diagnostic scripts
├── main.py                    # Application launch entry point
├── NewsArticleCollector.spec  # PyInstaller packaging configuration
├── requirements.txt           # Python dependency requirements
├── README.md                  # Project overview and quick start (this file)
├── USER_GUIDE.md              # End-user manual and operational guide
└── DEVELOPER.md               # Technical architecture and developer documentation
```

---

## Ethical Collection & Responsible Use Statement

This application is built for academic and research purposes. It exclusively collects publicly accessible news articles and public user comments available through standard site access. It does **not** bypass paywalls, solve CAPTCHAs, use proxy rotation, or bypass user authentication controls. Conservative request delays are enforced to respect source server bandwidth.
