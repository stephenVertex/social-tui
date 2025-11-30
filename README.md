# social-tui

Interactive TUI application for viewing and managing LinkedIn posts from JSON data sources.

## Features

### Interactive UI
- **Interactive Table View**: Browse LinkedIn posts in a clean table interface
- **Navigate**: Use arrow keys to move through posts
- **View Details**: Press `Enter` to see full post content
- **Multi-Action Marking**: Press `m` to quickly mark posts with 'save' action, or `M` to select multiple actions:
  - Queue for repost
  - Autoreact (like, celebrate, love)
  - Autocomment
  - Manual comment
  - Autorepost with thoughts
  - Manual repost with thoughts
  - Save for later
- **Mark from Detail View**: Mark posts with actions while viewing full post details
- **View TODOs**: Press `t` to see all marked posts in a popup
- **Export TODOs**: Press `q` to quit and print TODO list with action metadata to terminal
- **Save Marked Posts**: Press `s` to export marked posts with action metadata to JSON

### Data Management
- **SQLite Database**: Posts, profiles, tags, and engagement metrics stored in SQLite
- **AWS-Style Identifiers**: All entities use consistent AWS-style IDs (e.g., `p-a1b2c3d4`, `prf-9abc0def`)
- **Time-Series Tracking**: Track engagement metrics (reactions, comments) over time
- **Profile Management**: Organize LinkedIn profiles with tags
- **Download Run Tracking**: Audit trail of all scraping sessions
- **Automated Updates**: Single command to scrape, import, and view statistics

## Installation

```bash
# Install dependencies using uv
uv pip install -r pyproject.toml
```

Or install manually:
```bash
pip install rich textual
```

## Quick Start

### Initial Setup

1. **Install dependencies**:
```bash
uv pip install -r pyproject.toml
```

2. **Run database migration** (first time only):
```bash
python migrate_database.py --source data/posts.db --output data/posts_v2.db
```

3. **Prepare profile list** - Create `data/input-data.csv`:
```csv
name,username
Corey Quinn,coquinn
Jeff Barr,jeffbarr
Darko Mesaros,darko-mesaros
```

### Daily Workflow

**Update data (scrape + import + stats)**:
```bash
python update_data.py
```

This single command:
1. Scrapes latest LinkedIn posts via `run_apify.sh`
2. Imports data to database with time-series tracking
3. Displays statistics

**View posts interactively**:
```bash
./interactive_posts.py
```

## Usage

### 1. Prepare Input CSV

Create a `data/input-data.csv` file with LinkedIn profiles to track:

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

### 2. Update Data (Unified Command)

```bash
python update_data.py
```

**What it does:**
1. Runs `run_apify.sh` to scrape LinkedIn posts
2. Imports to database with download run tracking
3. Shows updated statistics

**Options:**
```bash
python update_data.py --skip-scrape      # Import only (skip scraping)
python update_data.py --date 20251129    # Import specific date
python update_data.py --no-stats         # Skip statistics display
```

**Alternative (manual steps):**
```bash
# Step 1: Scrape data
./run_apify.sh

# Step 2: Import to database
python manage_data.py import data/20251129/linkedin/

# Step 3: View statistics
python manage_data.py stats
```

### 3. View Posts Interactively

```bash
./interactive_posts.py
```

Or:
```bash
python interactive_posts.py
```

## Key Bindings

### Main Table View

| Key | Action |
|-----|--------|
| `↑`/`↓` or `j`/`k` | Navigate through posts |
| `Enter` | View full post details |
| `m` | Quick mark/unmark post with 'save' action |
| `M` (Shift+m) | Mark with multiple actions (opens action modal) |
| `t` | View TODO list (popup) |
| `s` | Save marked posts to JSON file |
| `r` | Start filtering posts |
| `n` | Toggle showing only new posts (DB mode only) |
| `o` | Open post URL in browser |
| `q` | Quit and print TODO list |
| `Ctrl+C` | Quit without printing TODOs |

### Post Detail View

| Key | Action |
|-----|--------|
| `Escape` | Return to list view |
| `m` | Quick mark/unmark post with 'save' action |
| `M` (Shift+m) | Mark with multiple actions (opens action modal) |
| `o` | Open post URL in browser |
| `r` | Show raw JSON data |
| `i` | View image(s) in terminal (Kitty terminal only) |

### Action Selection Modal

| Key | Action |
|-----|--------|
| `q` | Toggle "Queue for repost" |
| `a` | Toggle "Autoreact" |
| `c` | Toggle "Autocomment" |
| `n` | Toggle "Manual comment" |
| `t` | Toggle "Autorepost with thoughts" |
| `r` | Toggle "Manual repost with thoughts" |
| `s` | Toggle "Save" |
| `Escape` | Close modal and save selections |

## Project Structure

```
social-tui/
├── data/                      # Input data and scraped posts
│   ├── posts_v2.db           # SQLite database (new schema)
│   ├── posts.db              # SQLite database (legacy)
│   ├── input-data.csv        # Profile list
│   └── YYYYMMDD/             # Date-based scrape directories
│       └── linkedin/
│           └── *.json        # Raw LinkedIn post data
├── output/                    # Generated files (marked posts, reports)
├── cache/                     # Cached images
├── specs/                     # Database and feature specifications
├── interactive_posts.py       # Main TUI application
├── update_data.py            # Unified data update script
├── manage_data.py            # Database import/stats management
├── migrate_database.py       # Schema migration tool
├── migrate_historical_runs.py # Historical data backfill
├── profile_manager.py        # Profile CRUD operations
├── tag_manager.py            # Tag management
├── db_utils.py               # Database utilities (ID generation)
└── run_apify.sh              # LinkedIn scraper script
```

## Database Schema

The application uses SQLite with AWS-style identifiers for all entities.

### Core Tables

**Posts** (`p-xxxxxxxx`)
- Unique posts with metadata (author, timestamp, content, URL)
- Platform-agnostic design (currently LinkedIn)
- Read/marked status for UI

**DataDownloads** (`dl-xxxxxxxx`)
- Time-series metric snapshots (reactions, comments, reposts)
- Links to posts and download runs
- Enables engagement tracking over time

**DownloadRuns** (`run-xxxxxxxx`)
- Audit trail of scraping sessions
- Tracks stats (posts fetched, new, errors)
- System info for debugging

**Profiles** (`prf-xxxxxxxx`)
- LinkedIn profiles being monitored
- Active/inactive status
- Tag associations

**Tags** (`tag-xxxxxxxx`)
- Labels for organizing profiles
- Color-coded for UI
- Many-to-many with profiles

**ProfileTags** (`pft-xxxxxxxx`)
- Junction table for profile-tag relationships

### Future Tables (Schema Ready)

- **PostTags** (`ptg-xxxxxxxx`) - AI-powered post tagging
- **ActionQueue** (`act-xxxxxxxx`) - Queued actions (autoreact, comment, etc.)
- **PostMedia** (`med-xxxxxxxx`) - Media tracking with AI analysis

### Database Management

**Import data:**
```bash
python manage_data.py import data/20251129/linkedin/
```

**View statistics:**
```bash
python manage_data.py stats
```

**Migrate to new schema:**
```bash
python migrate_database.py --source data/posts.db --output data/posts_v2.db
```

**Backfill historical runs:**
```bash
python migrate_historical_runs.py
```

**Profile management:**
```python
from profile_manager import ProfileManager
pm = ProfileManager()

# Add profile
profile_id = pm.add_profile("jeffbarr", "Jeff Barr")

# Get all profiles
profiles = pm.get_all_profiles()

# Sync from CSV
pm.sync_from_csv("data/input-data.csv")
```

**Tag management:**
```python
from tag_manager import TagManager
tm = TagManager()

# Add tag
tag_id = tm.add_tag("aws", color="cyan")

# Tag a profile
tm.tag_profile(profile_id, tag_id)

# Get profiles by tag
profiles = pm.get_profiles_by_tag("aws")
```

## Files

### Core Application
- `main.py` - Entry point for the application
- `interactive_posts.py` - Main interactive TUI application
- `show_posts.py` - Simple table viewer (non-interactive)

### Database Management
- `update_data.py` - Unified update script (scrape + import + stats)
- `manage_data.py` - Database import and statistics
- `migrate_database.py` - Schema migration tool
- `migrate_historical_runs.py` - Historical data backfill
- `profile_manager.py` - Profile CRUD operations
- `tag_manager.py` - Tag management
- `db_utils.py` - Database utilities (AWS-style ID generation)

### Data Collection
- `run_apify.sh` - Scraper script for fetching LinkedIn posts
- `scripts/` - Utility scripts for data extraction and processing

### Data Files
- `data/posts_v2.db` - SQLite database (new schema)
- `data/input-data.csv` - List of LinkedIn profiles to track
- `data/YYYYMMDD/linkedin/*.json` - Scraped LinkedIn posts
- `output/` - Generated files (marked posts saved here automatically)

### Documentation
- `docs/` - Additional documentation files
- `specs/` - Database and feature specifications

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
- `media` (optional)

### Marked Posts Output

When you mark posts and press `s` to save, they are automatically saved to:
```
output/marked_posts_YYYYMMDD_HHMMSS.json
```

The output includes:
- Search metadata (date, filter query)
- Full post data for all marked posts
- Action metadata for each post with:
  - Selected actions (e.g., `["q", "a"]` for queue and autoreact)
  - Timestamp when the post was marked

#### Action Codes

Marked posts display action codes in the "Marked" column:
- `q` - Queue for repost
- `a` - Autoreact
- `c` - Autocomment
- `n` - Manual comment
- `t` - Autorepost with thoughts
- `r` - Manual repost with thoughts
- `s` - Save

Multiple actions are shown together (e.g., `aq` means autoreact and queue for repost).
