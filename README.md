# social-tui

Interactive TUI application for viewing and managing LinkedIn posts from JSON data sources.

## Features

- **Interactive Table View**: Browse LinkedIn posts in a clean table interface
- **Navigate**: Use arrow keys to move through posts
- **View Details**: Press `Enter` to see full post content
- **Mark Posts**: Press `m` to mark posts for follow-up
- **View TODOs**: Press `t` to see all marked posts in a popup
- **Export TODOs**: Press `q` to quit and print TODO list to terminal

## Installation

```bash
# Install dependencies using uv
uv pip install -r pyproject.toml
```

Or install manually:
```bash
pip install rich textual
```

## Usage

### 1. Prepare Input CSV

Create an `input-data.csv` file with LinkedIn profiles to track:

```csv
name,username
Corey Quinn,coquinn
Jeff Barr,jeffbarr
Darko Mesaros,darko-mesaros
```

**CSV Structure:**
- **Header row required**: `name,username`
- **name**: Full name of the LinkedIn user
- **username**: LinkedIn username (from their profile URL: `linkedin.com/in/{username}`)

### 2. Run Apify Scraper

```bash
./run_apify.sh
```

This will scrape LinkedIn posts and save JSON output to `data/{date}/linkedin/`.

### 3. View Posts Interactively

```bash
./interactive_posts.py
```

Or:
```bash
python interactive_posts.py
```

## Key Bindings

| Key | Action |
|-----|--------|
| `‘`/`“` | Navigate through posts |
| `Enter` | View full post details |
| `Escape` | Return to list view |
| `m` | Mark/unmark post for response |
| `t` | View TODO list (popup) |
| `q` | Quit and print TODO list |
| `Ctrl+C` | Quit without printing TODOs |

## Files

- `interactive_posts.py` - Main interactive TUI application
- `show_posts.py` - Simple table viewer (non-interactive)
- `run_apify.sh` - Scraper script for fetching LinkedIn posts
- `input-data.csv` - List of LinkedIn profiles to track (not included in repo)

## Data Structure

The application expects JSON files in this structure:
```
data/
 YYYYMMDD/
     linkedin/
         *.json
```

Each JSON file contains an array of post objects with fields like:
- `posted_at.date`
- `author.username`
- `author.name`
- `text`
- `url`
