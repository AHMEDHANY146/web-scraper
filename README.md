# 🚗 Car Listing Web Scraper

A production-grade, asynchronous web scraper built with Python and Playwright, designed to extract comprehensive car listing data from a large-scale automotive marketplace. The scraper handles thousands of listings while staying resilient against bot-detection systems, network failures, and memory pressure.

---

## ✨ Features

- **Dual Execution Modes** — Cloud mode via [Browserless.io](https://browserless.io) with stealth anti-bot, and a local headless/headed Chromium fallback.
- **Asynchronous & Concurrent** — Uses `asyncio` + Playwright to scrape multiple car detail pages in parallel, controlled by a configurable concurrency semaphore.
- **Crash-Resilient with Auto-Resume** — Progress is persisted to a JSON file after every batch. If the scraper crashes or is interrupted, simply re-run it and it picks up exactly where it left off.
- **Batched CSV Output** — Data is written in configurable batch sizes to avoid memory exhaustion. All batches are merged into a single clean CSV at the end.
- **Real-Time Telegram Notifications** — Start/resume events, per-batch CSV files, completion summaries, and crash alerts are pushed to a Telegram bot instantly.
- **Anti-Bot Evasion** — Realistic browser fingerprint (Chrome 122 User-Agent, 1280×720 viewport), stealth mode via Browserless, and deliberate wait times to mimic human browsing.
- **Memory-Efficient Browser Lifecycle** — Each browser instance is opened, used, and immediately closed to release all RAM before the next batch begins.
- **Exploration Script** — A standalone synchronous script for inspecting HTML structure and validating CSS selectors during development.

---

## 📁 Project Structure

```
web-scraber/
│
├── scraper.py          # Main scraper — cloud mode (Browserless.io) with stealth
├── localscraper.py     # Local mode — runs headed Chromium on your own machine
├── exploresite.py      # Dev utility — explore a single page interactively
├── config.py           # Centralized configuration (URLs, timeouts, batch sizes, etc.)
│
├── .env                # Secret keys (Telegram bot + Browserless API key) — not committed
├── .env.example        # Template showing required env vars
├── .gitignore          # Excludes .env, output/, and the venv directory
├── requirements.txt    # Python dependencies
└── output/             # Auto-created — contains batch CSVs and the final cars.csv
    ├── .progress.json  # Auto-resume checkpoint (created at runtime)
    ├── batch_1.csv
    ├── batch_2.csv
    └── cars.csv        # Final merged output
```

---

## ⚙️ Configuration (`config.py`)

All tunable parameters live in one place:

| Variable        | Default               | Description                                          |
|-----------------|-----------------------|------------------------------------------------------|
| `BASE_URL`      | *(target site)*       | Root URL of the marketplace                          |
| `LISTING_PATH`  | `/en/car/page/{page_num}` | URL template for paginated listing pages         |
| `TOTAL_PAGES`   | `5`                   | Number of listing pages to scrape                    |
| `BATCH_SIZE`    | `20`                  | Number of car links processed concurrently per chunk |
| `CONCURRENCY`   | `5`                   | Max simultaneous browser tabs during detail scraping |
| `MAX_RETRIES`   | `3`                   | Retry attempts per page/car before skipping          |
| `RETRY_DELAY`   | `5`                   | Seconds to wait between retry attempts               |
| `OUTPUT_DIR`    | `output`              | Directory where CSV files are saved                  |
| `OUTPUT_FILE`   | `cars.csv`            | Final merged CSV filename                            |
| `PROGRESS_FILE` | `output/.progress.json` | Checkpoint file for crash recovery                 |

---

## 🔐 Environment Variables (`.env`)

Create a `.env` file in the project root (use `.env.example` as a template):

```env
BOT_TOKEN=your_telegram_bot_token
CHAT_ID=your_telegram_chat_id
BROWSERLESS_API_KEY=your_browserless_api_key   # Optional — omit to use local Chromium
```

| Variable              | Required | Description                                                    |
|-----------------------|----------|----------------------------------------------------------------|
| `BOT_TOKEN`           | Yes      | Telegram Bot API token (create via [@BotFather](https://t.me/botfather)) |
| `CHAT_ID`             | Yes      | Your Telegram user/group Chat ID                              |
| `BROWSERLESS_API_KEY` | Optional | API key for [Browserless.io](https://browserless.io). If omitted, falls back to local Chromium |

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/web-scraber.git
cd web-scraber
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment

```bash
cp .env.example .env
# Then edit .env with your Telegram credentials and optional Browserless key
```

### 5. Adjust `config.py`

Set `TOTAL_PAGES` to the number of listing pages you want to scrape, and tune `BATCH_SIZE` and `CONCURRENCY` based on your machine's resources or your Browserless plan limits.

---

## ▶️ Running the Scraper

### Cloud Mode (recommended for large-scale runs)

Uses Browserless.io with `stealth=true` to bypass bot-detection. Requires `BROWSERLESS_API_KEY` in `.env`.

```bash
python scraper.py
```

### Local Mode (no API key needed)

Opens real Chromium windows on your machine. Best for testing or small runs.

```bash
python localscraper.py
```

### Exploration / Development Mode

Opens a single browser window, navigates to a test listing page, and prints all extracted fields to the console. Useful for debugging CSS selectors without running a full scrape.

```bash
python exploresite.py
```

---

## 🔄 How It Works

```
┌─────────────────────────────────────────────────────┐
│                   main() loop                        │
│                                                      │
│  For each page (1 → TOTAL_PAGES):                   │
│  ┌──────────────────────────────────────────────┐   │
│  │  1. Open browser → scrape listing page links │   │
│  │  2. Close browser immediately (free RAM)     │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  For each BATCH_SIZE chunk of links:                │
│  ┌──────────────────────────────────────────────┐   │
│  │  3. Open new browser + context               │   │
│  │  4. Run CONCURRENCY tabs simultaneously      │   │
│  │     → scrape car detail pages                │   │
│  │  5. Close browser immediately                │   │
│  │  6. Write batch_N.csv                        │   │
│  │  7. Send CSV to Telegram                     │   │
│  │  8. Save progress checkpoint                 │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  After all pages: Merge all batch CSVs → cars.csv   │
│                   Delete individual batch files      │
│                   Clear progress checkpoint          │
│                   Send completion summary            │
└─────────────────────────────────────────────────────┘
```

---

## 📊 Output Data Schema

Each row in `cars.csv` represents one vehicle listing with the following columns:

| Column               | Description                                      |
|----------------------|--------------------------------------------------|
| `title`              | Full car title (make, model, trim)               |
| `year`               | Manufacturing year                               |
| `km`                 | Mileage / kilometers driven                      |
| `transmission`       | Gearbox type (Automatic / Manual)                |
| `fuel`               | Fuel type (Petrol / Diesel / Electric / Hybrid)  |
| `price`              | Price in EGP (integer, cleaned of formatting)    |
| `description`        | Seller's free-text description                   |
| `url`                | Relative URL of the listing page                 |
| `detail_*`           | Dynamic columns from the car's details table     |
| `feature_*`          | Dynamic columns for each feature category        |

> **Dynamic columns**: `detail_*` and `feature_*` columns are generated from whatever keys/categories the website provides for that specific listing, so the schema adapts automatically to the data.

---

## 🛡️ Anti-Bot Evasion Layers

The scraper employs multiple techniques to avoid being blocked:

1. **Stealth Browser (Cloud mode)** — Connects to Browserless.io with `stealth=true`, which patches browser fingerprints that headless detection systems look for.
2. **Realistic User-Agent** — Sends a genuine Chrome 122 on Windows 10 User-Agent string.
3. **Realistic Viewport** — Browses at a standard 1280×720 resolution, not a headless default.
4. **Human-Like Wait Times** — Waits 5 seconds after every page navigation before extracting data, mimicking human reading time and allowing JS-rendered content to fully load.

---

## 🔁 Crash Recovery

The scraper saves a checkpoint to `output/.progress.json` after every batch:

```json
{
  "last_page": 3,
  "last_link_index": 39,
  "batch_count": 6
}
```

On the next run, it automatically detects this file and resumes from the exact page and link offset where it stopped. A Telegram message is sent to notify you whether a fresh run or a resume is starting.

Upon successful completion, the checkpoint file is deleted.

---

## 📬 Telegram Notifications

The bot sends the following events automatically:

| Event                  | Message type          |
|------------------------|-----------------------|
| Scraping started       | Text message          |
| Resuming after crash   | Text with page/offset |
| Each batch completed   | CSV file attachment   |
| Crash detected         | Text with error info  |
| Scraping finished      | Summary with stats    |

---

## 🧪 Development Tips

- Use `exploresite.py` to inspect and verify CSS selectors before modifying the main scraper. The `test_page_num` variable in `config.py` controls which page it lands on.
- Set `TOTAL_PAGES = 1` and `BATCH_SIZE = 5` in `config.py` for a quick sanity check run.
- To force a fresh scrape (ignore resume checkpoint), delete `output/.progress.json` manually.

---

## 📦 Dependencies

| Package          | Purpose                                              |
|------------------|------------------------------------------------------|
| `playwright`     | Browser automation (Chromium)                        |
| `requests`       | Telegram Bot API HTTP calls                          |
| `python-dotenv`  | Load environment variables from `.env`               |

Install all with:
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 📄 License

This project is licensed under the terms found in the [LICENSE](LICENSE) file.
