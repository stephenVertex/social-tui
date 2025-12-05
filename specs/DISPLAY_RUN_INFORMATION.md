# Display Run Information - Specification

**Status:** Implemented
**Created:** 2025-12-05
**Implemented:** 2025-12-05
**Priority:** Medium

## Overview

Add a new screen to the interactive posts viewer (`interactive_posts.py`) that displays historical information about download runs from the `download_runs` table. This provides users visibility into when data was fetched, how many posts were downloaded, engagement snapshots captured, and the status of each run.

## Goals

1. Provide visibility into download run history
2. Show key metrics for each run (posts fetched, new posts, engagement snapshots, duration)
3. Allow users to navigate and inspect run details
4. Show summary statistics across all runs
5. Help debug issues with data fetching

## User Stories

- As a user, I want to see when downloads last ran so I know if my data is current
- As a user, I want to see how many posts were fetched in each run to understand data volume
- As a user, I want to see how many new posts vs updates each run captured
- As a user, I want to see engagement snapshot counts to verify tracking is working
- As a user, I want to see if any runs failed so I can investigate issues
- As a user, I want to see run statistics (average duration, success rate, etc.)

## Data Source - `download_runs` Table

Based on exploration of project `qqadpocemndghvegozky`, the schema is:

### Core Columns
- `run_id` (text, PK) - Unique identifier like "run-771b1e56"
- `started_at` (timestamptz) - When the run started
- `completed_at` (timestamptz, nullable) - When the run completed (null if still running/failed)
- `status` (text) - 'running', 'completed', or 'failed' (default: 'running')
- `script_name` (text, nullable) - Name of script that ran (e.g., "update_data.py")
- `platform` (text) - Platform being scraped (default: 'linkedin')
- `posts_fetched` (integer) - Total posts fetched in this run (default: 0)
- `posts_new` (integer) - New posts discovered in this run (default: 0)
- `posts_updated` (integer) - Existing posts updated (default: 0)
- `error_message` (text, nullable) - Error details if run failed
- `system_info` (text, nullable) - JSON string with hostname, platform, script info
- `created_at` (timestamptz) - Record creation timestamp

### Related Data
- `data_downloads` table links to runs via `run_id` foreign key
- Each run captures engagement snapshots for posts
- Current data shows ~230 snapshots per run, tracking ~220 unique posts

### Current Statistics (from exploration)
- **Total runs:** 11
- **Completed:** 11
- **Failed:** 0
- **Running:** 0
- **Platform:** All LinkedIn
- **Average posts per run:** ~281
- **Total posts fetched:** 3,092
- **Total new posts discovered:** 174
- **Typical duration:** 22-71 seconds

## Screen Design

### Main Run History View

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Download Run History                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Date/Time            │ Status    │ Posts  │ New    │ Snaps  │ Duration     │
├──────────────────────┼───────────┼────────┼────────┼────────┼──────────────┤
│ 2025-12-05 19:49:05 │ ✓ Done    │    230 │     79 │    230 │   1m 11s    │
│ 2025-12-02 17:06:17 │ ✓ Done    │    230 │     26 │    230 │   1m  9s    │
│ 2025-12-01 19:56:19 │ ✓ Done    │    230 │      2 │    230 │     22.3s   │
│ 2025-12-01 17:56:08 │ ✓ Done    │    230 │     13 │    230 │     23.3s   │
│ 2025-11-30 15:51:33 │ ✓ Done    │    230 │     10 │    230 │     19.8s   │
└─────────────────────────────────────────────────────────────────────────────┘

Summary: 11 total runs │ 11 completed │ 0 failed │ Avg: 281 posts/run

[Footer: Enter=Details │ r=Refresh │ s=Stats │ Esc=Back]
```

**Columns:**
- **Date/Time:** Started timestamp
- **Status:** ✓ Done, ✗ Failed, ⟳ Running
- **Posts:** Total posts fetched (`posts_fetched`)
- **New:** New posts discovered (`posts_new`)
- **Snaps:** Engagement snapshots captured (count from `data_downloads`)
- **Duration:** Time from `started_at` to `completed_at`

### Run Detail View

When user presses Enter on a run:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Run Details                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Run ID:         run-771b1e56                                                │
│ Started:        2025-12-05 19:49:05 UTC                                     │
│ Completed:      2025-12-05 19:50:16 UTC                                     │
│ Duration:       1 minute 11 seconds                                         │
│ Status:         ✓ Completed                                                  │
│                                                                              │
│ ──────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│ Data Collection:                                                             │
│   Platform:         LinkedIn                                                │
│   Script:           update_data.py                                          │
│   Posts Fetched:    230 posts                                               │
│   New Posts:        79 posts (34.3%)                                        │
│   Updated Posts:    0 posts                                                 │
│   Snapshots:        230 engagement snapshots                                │
│   Unique Posts:     221 posts tracked                                       │
│                                                                              │
│ System Info:                                                                 │
│   Hostname:         pompom                                                  │
│                                                                              │
│ Performance:                                                                 │
│   Posts/second:     3.2 posts/sec                                           │
│   Avg time/post:    0.31 seconds                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

[Footer: Esc=Back │ c=Copy Run ID │ p=View Posts]
```

### Failed Run Detail View

For failed runs (when implemented), show error information:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Run Details                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Run ID:         run-abc12345                                                │
│ Started:        2025-12-04 20:15:33 UTC                                     │
│ Failed:         2025-12-04 20:15:35 UTC                                     │
│ Duration:       2.3 seconds                                                  │
│ Status:         ✗ Failed                                                     │
│                                                                              │
│ ──────────────────────────────────────────────────────────────────────────  │
│                                                                              │
│ Error:                                                                       │
│   Database connection timeout: Could not connect to Supabase                │
│   at host db.example.supabase.co after 3 retry attempts.                    │
│                                                                              │
│ Data Collection:                                                             │
│   Platform:         LinkedIn                                                │
│   Script:           update_data.py                                          │
│   Posts Fetched:    0 posts                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

[Footer: Esc=Back │ c=Copy Error]
```

### Statistics Dashboard View

When user presses 's' for statistics:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Run Statistics                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Overall Performance:                                                         │
│   Total Runs:           11                                                  │
│   Successful:           11 (100.0%)                                         │
│   Failed:               0 (0.0%)                                            │
│   Currently Running:    0                                                   │
│                                                                              │
│ Post Collection:                                                             │
│   Total Posts Fetched:  3,092 posts                                         │
│   Total New Posts:      174 posts                                           │
│   Average per Run:      281 posts                                           │
│   Max in Single Run:    356 posts                                           │
│   Min in Single Run:    230 posts                                           │
│                                                                              │
│ Platform Breakdown:                                                          │
│   LinkedIn:             11 runs (100%)                                      │
│                                                                              │
│ Timing:                                                                      │
│   Average Duration:     45.2 seconds                                        │
│   Fastest Run:          19.8 seconds                                        │
│   Slowest Run:          1m 11s                                              │
│                                                                              │
│ Recent Activity:                                                             │
│   Last Run:             2025-12-05 19:49:05 (3 hours ago)                   │
│   Last Success:         2025-12-05 19:49:05 (3 hours ago)                   │
│   Runs Last 24h:        1                                                   │
│   Runs Last 7d:         5                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

[Footer: Esc=Back]
```

## Features

### Core Features (MVP)

1. **Run History List**
   - Display runs in reverse chronological order (newest first)
   - Show key columns: Date/Time, Status, Posts, New, Snapshots, Duration
   - Color-code status (green for completed, red for failed, yellow for running)
   - Show all runs (no pagination needed for current 11 runs)

2. **Run Detail View**
   - Show comprehensive information for a single run
   - Display timing information (started, completed, duration)
   - Show post counts (total, new, updated)
   - Show engagement snapshot counts
   - Parse and display system_info JSON
   - Calculate performance metrics (posts/second)
   - For failed runs, display error messages

3. **Statistics Dashboard**
   - Overall performance (success rate, total runs)
   - Post collection statistics (total, average, min/max)
   - Platform breakdown
   - Timing statistics (average, min, max duration)
   - Recent activity summary

4. **Navigation**
   - Up/down arrow keys (or j/k) to navigate run list
   - Enter to view run details
   - 's' to view statistics dashboard
   - Escape to go back to main screen
   - 'r' key to refresh run list

5. **Status Bar**
   - Show summary: "X total runs | Y completed | Z failed | Avg: N posts/run"

### Enhanced Features (Future)

1. **Filtering**
   - Filter by date range
   - Filter by status (completed/failed/running)
   - Filter by minimum post count

2. **Post Navigation**
   - From run detail view, press 'p' to view posts from that specific run
   - Filter main post list by run_id

3. **Comparison View**
   - Compare two runs side-by-side
   - Show deltas in post counts, duration, etc.

4. **Export**
   - Export run history to CSV
   - Export specific run details to JSON

5. **Charts/Graphs**
   - Timeline of post volume over time
   - Success rate trending
   - Duration trending

## Technical Implementation

### Database Queries

```python
# Get run history
def load_runs():
    """Load all download runs with engagement snapshot counts."""
    query = """
        SELECT
            dr.run_id,
            dr.started_at,
            dr.completed_at,
            dr.status,
            dr.script_name,
            dr.platform,
            dr.posts_fetched,
            dr.posts_new,
            dr.posts_updated,
            dr.error_message,
            dr.system_info,
            EXTRACT(EPOCH FROM (dr.completed_at - dr.started_at)) as duration_seconds,
            COUNT(dd.download_id) as snapshot_count,
            COUNT(DISTINCT dd.post_id) as unique_posts_tracked
        FROM download_runs dr
        LEFT JOIN data_downloads dd ON dr.run_id = dd.run_id
        GROUP BY dr.run_id, dr.started_at, dr.completed_at, dr.status,
                 dr.script_name, dr.platform, dr.posts_fetched, dr.posts_new,
                 dr.posts_updated, dr.error_message, dr.system_info
        ORDER BY dr.started_at DESC
    """
    return client.execute(query).data

# Get run statistics
def get_run_statistics():
    """Calculate aggregate statistics across all runs."""
    query = """
        SELECT
            COUNT(*) as total_runs,
            COUNT(*) FILTER (WHERE status = 'completed') as completed_runs,
            COUNT(*) FILTER (WHERE status = 'failed') as failed_runs,
            COUNT(*) FILTER (WHERE status = 'running') as running_runs,
            SUM(posts_fetched) as total_posts_fetched,
            SUM(posts_new) as total_new_posts,
            AVG(posts_fetched) as avg_posts_per_run,
            MAX(posts_fetched) as max_posts_in_run,
            MIN(posts_fetched) as min_posts_in_run,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds,
            MAX(EXTRACT(EPOCH FROM (completed_at - started_at))) as max_duration_seconds,
            MIN(EXTRACT(EPOCH FROM (completed_at - started_at))) as min_duration_seconds,
            MAX(started_at) as last_run_at,
            MAX(started_at) FILTER (WHERE status = 'completed') as last_success_at,
            COUNT(*) FILTER (WHERE started_at > NOW() - INTERVAL '24 hours') as runs_24h,
            COUNT(*) FILTER (WHERE started_at > NOW() - INTERVAL '7 days') as runs_7d
        FROM download_runs
    """
    return client.execute(query).data[0]

# Get platform breakdown
def get_platform_breakdown():
    """Get run counts by platform."""
    query = """
        SELECT
            platform,
            COUNT(*) as run_count,
            SUM(posts_fetched) as total_posts
        FROM download_runs
        GROUP BY platform
        ORDER BY run_count DESC
    """
    return client.execute(query).data
```

### Screen Classes

```python
class RunHistoryScreen(Screen):
    """Screen to show download run history."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "show_stats", "Stats"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id
        self.runs = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="summary-bar")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Setup table and load data."""
        table = self.query_one(DataTable)
        table.add_column("Date/Time", key="datetime")
        table.add_column("Status", key="status")
        table.add_column("Posts", key="posts")
        table.add_column("New", key="new")
        table.add_column("Snaps", key="snaps")
        table.add_column("Duration", key="duration")

        self.load_runs()
        table.focus()

    def load_runs(self):
        """Load and display run history."""
        try:
            # Execute query to get runs with snapshot counts
            self.runs = load_runs()

            # Calculate summary statistics
            total = len(self.runs)
            completed = sum(1 for r in self.runs if r['status'] == 'completed')
            failed = sum(1 for r in self.runs if r['status'] == 'failed')
            avg_posts = sum(r['posts_fetched'] for r in self.runs) / total if total > 0 else 0

            # Update summary bar
            summary = self.query_one("#summary-bar", Static)
            summary.update(
                f"Summary: {total} total runs │ {completed} completed │ "
                f"{failed} failed │ Avg: {avg_posts:.0f} posts/run"
            )

            # Populate table
            table = self.query_one(DataTable)
            table.clear()

            for run in self.runs:
                self._add_run_to_table(run, table)

        except Exception as e:
            self.notify(f"Error loading runs: {e}", severity="error")

    def _add_run_to_table(self, run: dict, table: DataTable):
        """Add a single run to the table."""
        # Format datetime
        dt = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")

        # Format status with emoji
        status_map = {
            'completed': '✓ Done',
            'failed': '✗ Failed',
            'running': '⟳ Running'
        }
        status = status_map.get(run['status'], run['status'])

        # Format duration
        duration = self._format_duration(run.get('duration_seconds'))

        table.add_row(
            dt_str,
            status,
            str(run['posts_fetched']),
            str(run['posts_new']),
            str(run.get('snapshot_count', 0)),
            duration
        )

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"

        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs:2d}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins:2d}m"

    def on_data_table_row_selected(self, event):
        """Handle row selection to show run details."""
        if event.cursor_row < len(self.runs):
            run = self.runs[event.cursor_row]
            self.app.push_screen(RunDetailScreen(run))

    def action_refresh(self):
        """Refresh the run list."""
        self.load_runs()
        self.notify("Run list refreshed", timeout=2)

    def action_show_stats(self):
        """Show statistics dashboard."""
        self.app.push_screen(RunStatisticsScreen(self.project_id))

    def action_dismiss(self):
        """Return to main screen."""
        self.app.pop_screen()


class RunDetailScreen(Screen):
    """Screen to show details of a specific run."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("c", "copy_run_id", "Copy Run ID"),
    ]

    def __init__(self, run_data: dict):
        super().__init__()
        self.run_data = run_data

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_run_details(), id="run-detail")
        )
        yield Footer()

    def _format_run_details(self) -> str:
        """Format run data for display."""
        run = self.run_data

        # Parse system_info JSON
        system_info = {}
        if run.get('system_info'):
            try:
                system_info = json.loads(run['system_info'])
            except:
                pass

        # Format timestamps
        started = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
        completed = None
        if run.get('completed_at'):
            completed = datetime.fromisoformat(run['completed_at'].replace('Z', '+00:00'))

        # Calculate stats
        duration_seconds = run.get('duration_seconds', 0)
        posts_fetched = run.get('posts_fetched', 0)
        posts_per_sec = posts_fetched / duration_seconds if duration_seconds > 0 else 0
        sec_per_post = duration_seconds / posts_fetched if posts_fetched > 0 else 0
        new_pct = (run.get('posts_new', 0) / posts_fetched * 100) if posts_fetched > 0 else 0

        lines = [
            f"[bold cyan]Run ID:[/bold cyan] {run['run_id']}",
            f"[bold cyan]Started:[/bold cyan] {started.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        ]

        if completed:
            lines.append(f"[bold cyan]Completed:[/bold cyan] {completed.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            lines.append(f"[bold cyan]Duration:[/bold cyan] {self._format_duration(duration_seconds)}")

        status_display = {
            'completed': '✓ Completed',
            'failed': '✗ Failed',
            'running': '⟳ Running'
        }.get(run['status'], run['status'])

        lines.append(f"[bold cyan]Status:[/bold cyan] {status_display}")
        lines.append("")
        lines.append("─" * 76)
        lines.append("")
        lines.append("[bold]Data Collection:[/bold]")
        lines.append(f"  Platform:         {run.get('platform', 'N/A').title()}")
        lines.append(f"  Script:           {run.get('script_name', 'N/A')}")
        lines.append(f"  Posts Fetched:    {posts_fetched} posts")
        lines.append(f"  New Posts:        {run.get('posts_new', 0)} posts ({new_pct:.1f}%)")
        lines.append(f"  Updated Posts:    {run.get('posts_updated', 0)} posts")
        lines.append(f"  Snapshots:        {run.get('snapshot_count', 0)} engagement snapshots")
        lines.append(f"  Unique Posts:     {run.get('unique_posts_tracked', 0)} posts tracked")

        if system_info:
            lines.append("")
            lines.append("[bold]System Info:[/bold]")
            if 'hostname' in system_info:
                lines.append(f"  Hostname:         {system_info['hostname']}")

        if duration_seconds > 0 and posts_fetched > 0:
            lines.append("")
            lines.append("[bold]Performance:[/bold]")
            lines.append(f"  Posts/second:     {posts_per_sec:.1f} posts/sec")
            lines.append(f"  Avg time/post:    {sec_per_post:.2f} seconds")

        if run.get('error_message'):
            lines.append("")
            lines.append("[bold red]Error:[/bold red]")
            lines.append(f"  {run['error_message']}")

        return "\n".join(lines)

    def _format_duration(self, seconds: float) -> str:
        """Format duration string."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins} minute{'s' if mins != 1 else ''} {secs} seconds"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours} hour{'s' if hours != 1 else ''} {mins} minutes"

    def action_copy_run_id(self):
        """Copy run ID to clipboard."""
        try:
            subprocess.run(
                ['pbcopy'],
                input=self.run_data['run_id'].encode('utf-8'),
                check=True
            )
            self.notify("Run ID copied to clipboard!", severity="information")
        except Exception as e:
            self.notify(f"Error copying to clipboard: {e}", severity="error")

    def action_dismiss(self):
        """Return to run history."""
        self.app.pop_screen()


class RunStatisticsScreen(Screen):
    """Screen to show aggregate statistics across all runs."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
    ]

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_statistics(), id="statistics")
        )
        yield Footer()

    def on_mount(self):
        """Load statistics on mount."""
        try:
            stats = get_run_statistics()
            platforms = get_platform_breakdown()

            display = self.query_one("#statistics", Static)
            display.update(self._format_statistics(stats, platforms))
        except Exception as e:
            self.notify(f"Error loading statistics: {e}", severity="error")

    def _format_statistics(self, stats: dict = None, platforms: list = None) -> str:
        """Format statistics for display."""
        if not stats:
            return "Loading statistics..."

        # Calculate percentages
        total = stats['total_runs']
        success_pct = (stats['completed_runs'] / total * 100) if total > 0 else 0
        fail_pct = (stats['failed_runs'] / total * 100) if total > 0 else 0

        # Format last run time
        last_run = "Never"
        if stats.get('last_run_at'):
            last_run_dt = datetime.fromisoformat(stats['last_run_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = now - last_run_dt
            last_run = self._format_relative_time(delta)

        lines = [
            "[bold]Overall Performance:[/bold]",
            f"  Total Runs:           {stats['total_runs']}",
            f"  Successful:           {stats['completed_runs']} ({success_pct:.1f}%)",
            f"  Failed:               {stats['failed_runs']} ({fail_pct:.1f}%)",
            f"  Currently Running:    {stats['running_runs']}",
            "",
            "[bold]Post Collection:[/bold]",
            f"  Total Posts Fetched:  {stats['total_posts_fetched']:,} posts",
            f"  Total New Posts:      {stats['total_new_posts']:,} posts",
            f"  Average per Run:      {stats['avg_posts_per_run']:.0f} posts",
            f"  Max in Single Run:    {stats['max_posts_in_run']} posts",
            f"  Min in Single Run:    {stats['min_posts_in_run']} posts",
            "",
        ]

        if platforms:
            lines.append("[bold]Platform Breakdown:[/bold]")
            for p in platforms:
                pct = (p['run_count'] / total * 100) if total > 0 else 0
                lines.append(f"  {p['platform'].title():<15} {p['run_count']} runs ({pct:.0f}%)")
            lines.append("")

        lines.extend([
            "[bold]Timing:[/bold]",
            f"  Average Duration:     {self._format_duration_short(stats.get('avg_duration_seconds'))}",
            f"  Fastest Run:          {self._format_duration_short(stats.get('min_duration_seconds'))}",
            f"  Slowest Run:          {self._format_duration_short(stats.get('max_duration_seconds'))}",
            "",
            "[bold]Recent Activity:[/bold]",
            f"  Last Run:             {last_run}",
            f"  Runs Last 24h:        {stats.get('runs_24h', 0)}",
            f"  Runs Last 7d:         {stats.get('runs_7d', 0)}",
        ])

        return "\n".join(lines)

    def _format_duration_short(self, seconds: float) -> str:
        """Format duration in short format."""
        if seconds is None:
            return "N/A"
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"

    def _format_relative_time(self, delta: timedelta) -> str:
        """Format a time delta as relative time."""
        seconds = delta.total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds // 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(seconds // 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"

    def action_dismiss(self):
        """Return to run history."""
        self.app.pop_screen()
```

### Integration with MainScreen

Add binding to MainScreen in `interactive_posts.py`:

```python
class MainScreen(Screen):
    BINDINGS = [
        # ... existing bindings ...
        Binding("h", "show_run_history", "Run History"),
    ]

    def action_show_run_history(self):
        """Show run history screen."""
        if not self.use_db:
            self.notify("Run history only available with database backend", severity="warning")
            return

        # Get project ID from environment or config
        project_id = "qqadpocemndghvegozky"  # TODO: Make this configurable
        self.app.push_screen(RunHistoryScreen(project_id))
```

## Data Formatting

### Duration Formatting
- < 60s: "X.Xs" (e.g., "45.2s")
- >= 60s: "Xm Ys" (e.g., "2m 15s")
- >= 3600s: "Xh Ym" (e.g., "1h 5m")

### Status Indicators
- Completed: ✓ or green text
- Failed: ✗ or red text
- Running: ⟳ or yellow text

### Relative Time
- < 1 min: "just now"
- < 1 hour: "X minutes ago"
- < 24 hours: "X hours ago"
- >= 24 hours: "X days ago"

### Date/Time Display
- Full timestamp: "YYYY-MM-DD HH:MM:SS"
- With timezone: "YYYY-MM-DD HH:MM:SS UTC"

## Error Handling

1. **No Database Connection**
   - Show friendly error message
   - Disable run history feature in UI

2. **No Runs Found**
   - Display "No download runs found" message
   - Suggest running a download

3. **Failed to Load Run Details**
   - Show error notification
   - Return to run history list

4. **Database Query Timeout**
   - Show timeout message
   - Offer retry option via 'r' key

5. **Missing/Invalid Data**
   - Handle null values gracefully
   - Show "N/A" for missing fields
   - Parse JSON fields with try/except

## Testing Scenarios

1. **Normal Operation**
   - All runs completed successfully
   - Verify table displays correctly
   - Verify detail view shows all info

2. **Failed Run**
   - Run with error_message
   - Verify error displays in detail view

3. **Running Download**
   - Run with status='running' and null completed_at
   - Verify duration shows "N/A"
   - Verify status shows "⟳ Running"

4. **Empty Database**
   - No runs exist yet
   - Verify empty state displays correctly

5. **Large Dataset**
   - 100+ runs in database
   - Verify performance is acceptable
   - Consider pagination if needed

6. **Statistics View**
   - Verify all calculations are correct
   - Test with various data scenarios

## Performance Considerations

1. **Single Query Load**
   - Load all runs with JOINed snapshot counts in one query
   - No N+1 query problem

2. **Caching**
   - Cache run list for short duration (30 seconds)
   - Invalidate cache on refresh ('r' key)

3. **Database Indexes**
   - Ensure `started_at` is indexed for sorting
   - Ensure `run_id` foreign key is indexed in data_downloads

## Future Enhancements

1. **Post Navigation**
   - From run detail, show which posts were discovered/updated
   - Link to main post view filtered by run

2. **Comparison View**
   - Select two runs to compare side-by-side
   - Show deltas (new posts increase/decrease, etc.)

3. **Filtering**
   - Filter by date range
   - Filter by status
   - Filter by platform (when multiple platforms added)

4. **Export**
   - Export run history to CSV
   - Export statistics to JSON

5. **Charts**
   - ASCII charts for trends over time
   - Post volume timeline
   - Success rate trending

6. **Live Updates**
   - Auto-refresh when run is in progress
   - Show real-time progress

## Dependencies

- Existing Supabase client (via `mcp__supabase__execute_sql`)
- Textual framework (already in use)
- No new external dependencies required

## Success Criteria

1. ✓ Users can view a list of download runs
2. ✓ Users can see key metrics for each run at a glance
3. ✓ Users can drill into details of any run
4. ✓ Failed runs clearly show error information (when they exist)
5. ✓ Statistics dashboard shows aggregate metrics
6. ✓ Screen integrates seamlessly with existing TUI
7. ✓ Performance is acceptable with current dataset (11 runs)

## Open Questions

1. Should we paginate if run count grows large (e.g., >100)?
2. How long should we retain run history in the database?
3. Should there be a way to manually trigger a download from this screen?
4. Should we show which specific profiles were scraped during each run?
5. Do we need real-time updates for currently running downloads?

## Implementation Plan

1. Create new screen classes (RunHistoryScreen, RunDetailScreen, RunStatisticsScreen)
2. Add database query functions using Supabase MCP tools
3. Integrate with MainScreen (add 'h' keybinding)
4. Test with current dataset
5. Handle edge cases (failed runs, running downloads, empty state)
6. Document usage in README
