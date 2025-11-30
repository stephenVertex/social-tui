#!/usr/bin/env python3
"""
Interactive LinkedIn posts viewer with marking and TODO list functionality.
Now supports Supabase database backend for deduplication and management.
"""

import json
import glob
import argparse
import base64
import sys
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from supabase_client import get_supabase_client
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static, Input, Checkbox
from textual.containers import Container, VerticalScroll, Horizontal
from textual.binding import Binding
from textual.screen import Screen
from textual import events

# Cache directory for downloaded images
CACHE_DIR = Path("cache/images")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cached_image_path(image_url: str) -> Path:
    """
    Get the cached image path for a given URL.
    Creates a cache filename based on MD5 hash of the URL.

    Args:
        image_url: URL of the image

    Returns:
        Path to the cached image file
    """
    # Generate MD5 hash of URL
    url_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()

    # Try to determine extension from URL
    from urllib.parse import urlparse
    parsed = urlparse(image_url)
    path = parsed.path.lower()

    # Default to jpg if we can't determine extension
    ext = '.jpg'
    if '.png' in path:
        ext = '.png'
    elif '.gif' in path:
        ext = '.gif'
    elif '.webp' in path:
        ext = '.webp'

    return CACHE_DIR / f"{url_hash}{ext}"


def download_image(image_url: str) -> bytes:
    """
    Download an image from URL with proper User-Agent header.

    Args:
        image_url: URL of the image

    Returns:
        Image data as bytes
    """
    from urllib.request import Request, urlopen

    req = Request(
        image_url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }
    )
    with urlopen(req, timeout=10) as response:
        return response.read()


def get_image_data(image_url: str) -> bytes:
    """
    Get image data, using cache if available, otherwise download and cache.

    Args:
        image_url: URL or path to the image

    Returns:
        Image data as bytes
    """
    from urllib.parse import urlparse

    parsed = urlparse(image_url)

    # If it's a local file, just read it
    if parsed.scheme not in ('http', 'https'):
        with open(image_url, 'rb') as f:
            return f.read()

    # Check cache first
    cache_path = get_cached_image_path(image_url)
    if cache_path.exists():
        print(f"Using cached image: {cache_path.name}")
        with open(cache_path, 'rb') as f:
            return f.read()

    # Download and cache
    print(f"Downloading image...")
    image_data = download_image(image_url)

    # Save to cache
    with open(cache_path, 'wb') as f:
        f.write(image_data)
    print(f"Cached image: {cache_path.name}")

    return image_data


def display_image_kitty_to_terminal(image_url: str):
    """
    Display an image directly to the terminal using Kitty's icat or graphics protocol.
    This bypasses Textual and writes directly to stdout.

    Args:
        image_url: URL or path to the image
    """
    import subprocess
    import tempfile
    from urllib.request import urlopen
    from urllib.parse import urlparse

    try:
        # Get image data (from cache or download)
        image_data = get_image_data(image_url)

        # Method 1: Try using icat command (most reliable for Kitty)
        try:
            # Try different icat command variations
            icat_cmd = None
            for cmd in ['kitty', 'icat', '/Applications/Kitty.app/Contents/MacOS/kitty']:
                try:
                    result = subprocess.run([cmd, '+icat' if cmd == 'kitty' else '--version'],
                                          capture_output=True,
                                          timeout=1)
                    if result.returncode == 0:
                        icat_cmd = [cmd, '+icat'] if cmd == 'kitty' else [cmd]
                        break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue

            if not icat_cmd:
                raise FileNotFoundError("icat not found")

            # Save to temp file
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name

            # Display with icat
            print(f"Image size: {len(image_data):,} bytes\n")
            display_cmd = icat_cmd + ['--align', 'left', tmp_path]
            subprocess.run(display_cmd)

            # Clean up
            Path(tmp_path).unlink()
            return

        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # icat not available, fall through to method 2
            pass

        # Method 2: Use Kitty graphics protocol directly
        print(f"Image size: {len(image_data):,} bytes")

        # Encode image as base64
        encoded = base64.standard_b64encode(image_data).decode('ascii')

        # Split into chunks
        chunk_size = 4096
        chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
        print(f"Transmitting {len(chunks)} chunks...\n")

        # Output Kitty graphics protocol escape sequences
        for i, chunk in enumerate(chunks):
            if i == 0:
                sys.stdout.buffer.write(f"\033_Ga=T,f=100;{chunk}\033\\".encode('ascii'))
            elif i == len(chunks) - 1:
                sys.stdout.buffer.write(f"\033_Gm=0;{chunk}\033\\".encode('ascii'))
            else:
                sys.stdout.buffer.write(f"\033_Gm=1;{chunk}\033\\".encode('ascii'))

        sys.stdout.buffer.flush()
        print("\n(Image should appear above if you're in Kitty terminal)")

    except Exception as e:
        print(f"Error loading image: {e}")
        print(f"\nImage URL: {image_url}")
        print("You can open this URL in a browser to view the image.")


class RawJsonScreen(Screen):
    """Screen to show raw JSON data."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("c", "copy_json", "Copy JSON"),
    ]

    def __init__(self, post_data: dict):
        super().__init__()
        self.post_data = post_data

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_json(), id="raw-json", markup=False)
        )
        yield Footer()

    def _format_json(self) -> str:
        """Format post data as pretty JSON."""
        def json_serializer(obj):
            """Handle datetime serialization."""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        return json.dumps(self.post_data, indent=2, default=json_serializer)

    def action_dismiss(self):
        """Return to previous screen."""
        self.app.pop_screen()

    def action_copy_json(self):
        """Copy raw JSON to clipboard."""
        json_str = self._format_json()
        try:
            # Use pbcopy on macOS to copy to clipboard
            process = subprocess.run(
                ['pbcopy'],
                input=json_str.encode('utf-8'),
                check=True
            )
            self.notify("JSON copied to clipboard!", severity="information")
        except Exception as e:
            self.notify(f"Error copying to clipboard: {e}", severity="error")


class PostDetailScreen(Screen):
    """Screen to show full post details."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("r", "show_raw", "Raw JSON"),
        Binding("i", "show_image", "View Image"),
        Binding("o", "open_url", "Open URL"),
        Binding("m", "mark_post", "Mark Post (Save)"),
        Binding("M", "mark_with_actions", "Mark with Actions", key_display="shift+m"),
    ]

    def __init__(self, post_data: dict, post_idx: int, current_actions: set,
                 update_callback, use_kitty_images: bool = False):
        super().__init__()
        self.post_data = post_data
        self.post_idx = post_idx
        self.current_actions = current_actions
        self.update_callback = update_callback
        self.use_kitty_images = use_kitty_images

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_post(), id="post-detail")
        )
        yield Footer()

    def _format_post(self) -> str:
        """Format post data for display."""
        author = self.post_data.get("author", {})
        posted_at = self.post_data.get("posted_at", {})

        # Construct name from first_name and last_name if 'name' field doesn't exist
        name = author.get('name')
        if not name:
            first_name = author.get('first_name', '')
            last_name = author.get('last_name', '')
            name = f"{first_name} {last_name}".strip() or 'N/A'

        lines = [
            f"[bold cyan]Date:[/bold cyan] {posted_at.get('date', 'N/A')}",
            f"[bold cyan]Author:[/bold cyan] {author.get('username', 'N/A')}",
            f"[bold cyan]Name:[/bold cyan] {name}",
            f"[bold cyan]URL:[/bold cyan] {self.post_data.get('url', 'N/A')}",
        ]

        # Add marked status
        if self.current_actions:
            actions_display = ''.join(sorted(self.current_actions))
            lines.append(f"[bold cyan]Marked:[/bold cyan] [bold green]{actions_display}[/bold green]")
        else:
            lines.append(f"[bold cyan]Marked:[/bold cyan] No")

        # Add engagement data if available
        # Check both 'stats' (current format) and 'engagement' (legacy/alternative format)
        engagement = self.post_data.get("stats", self.post_data.get("engagement", {}))
        engagement_history = self.post_data.get("engagement_history", [])

        if engagement or engagement_history:
            lines.append("")
            lines.append("[bold cyan]Engagement:[/bold cyan]")

            # Check if we have historical data to show growth
            if engagement_history and len(engagement_history) > 1:
                # Use the latest historical snapshot as current if available
                current = engagement_history[-1]
                previous = engagement_history[-2]

                # Display historical timeline table first
                lines.append("")
                lines.append("[bold]Historical Timeline:[/bold]")
                lines.append("┌─────────────────────┬────────────┬──────────┬──────────┐")
                lines.append("│ Date                │ Reactions  │ Comments │ Reposts  │")
                lines.append("├─────────────────────┼────────────┼──────────┼──────────┤")

                # Show up to 10 most recent snapshots
                display_history = engagement_history[-10:] if len(engagement_history) > 10 else engagement_history
                for snapshot in display_history:
                    date_str = snapshot.get("_downloaded_at", "")
                    try:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        date_display = dt.strftime("%b %d %H:%M")
                    except:
                        date_display = date_str[:16] if len(date_str) > 16 else date_str

                    reactions = snapshot.get("total_reactions", snapshot.get("reactions", 0))
                    comments = snapshot.get("comments", 0)
                    reposts = snapshot.get("reposts", 0)

                    lines.append(f"│ {date_display:<19} │ {reactions:>10} │ {comments:>8} │ {reposts:>8} │")

                lines.append("└─────────────────────┴────────────┴──────────┴──────────┘")

                # Display summary with trend
                lines.append("")
                lines.append("[bold]Summary:[/bold]")
                lines.append("┌─────────────────┬──────────┬──────────┬────────────┐")
                lines.append("│ Metric          │ Current  │ Change   │ Trend      │")
                lines.append("├─────────────────┼──────────┼──────────┼────────────┤")

                metric_keys = [
                    ("Reactions", "total_reactions", "reactions"),
                    ("Comments", "comments", None),
                    ("Reposts", "reposts", "shares"),
                ]

                # Add views if available
                if current.get("views") is not None:
                    metric_keys.append(("Views", "views", None))

                for metric_name, primary_key, fallback_key in metric_keys:
                    current_val = current.get(primary_key, current.get(fallback_key, 0) if fallback_key else 0)
                    prev_val = previous.get(primary_key, previous.get(fallback_key, 0) if fallback_key else 0)

                    change = current_val - prev_val
                    change_str = f"+{change}" if change > 0 else str(change)

                    # Create simple ASCII trend visualization
                    if change > 0:
                        trend = "↗ " + "▂" * min(int(change / max(prev_val, 1) * 10), 8)
                    elif change < 0:
                        trend = "↘ "
                    else:
                        trend = "→ "

                    lines.append(f"│ {metric_name:<15} │ {current_val:>8} │ {change_str:>8} │ {trend:<10} │")

                lines.append("└─────────────────┴──────────┴──────────┴────────────┘")

                # Show overall statistics
                lines.append("")
                first_snapshot = engagement_history[0]
                last_snapshot = engagement_history[-1]

                reactions_total_growth = last_snapshot.get("total_reactions", last_snapshot.get("reactions", 0)) - first_snapshot.get("total_reactions", first_snapshot.get("reactions", 0))
                comments_total_growth = last_snapshot.get("comments", 0) - first_snapshot.get("comments", 0)
                reposts_total_growth = last_snapshot.get("reposts", 0) - first_snapshot.get("reposts", 0)

                # Show time range
                first_time = first_snapshot.get("_downloaded_at", "")
                last_time = last_snapshot.get("_downloaded_at", "")
                if first_time and last_time:
                    try:
                        first_dt = datetime.fromisoformat(first_time.replace('Z', '+00:00'))
                        last_dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                        days_elapsed = (last_dt - first_dt).total_seconds() / 86400
                        time_range = f"{first_dt.strftime('%b %d')} → {last_dt.strftime('%b %d %H:%M')}"
                        lines.append(f"[dim]Tracked: {time_range} ({len(engagement_history)} snapshots over {days_elapsed:.1f} days)[/dim]")
                    except:
                        lines.append(f"[dim]Tracked: {len(engagement_history)} snapshots[/dim]")

                if reactions_total_growth != 0 or comments_total_growth != 0 or reposts_total_growth != 0:
                    growth_parts = []
                    if reactions_total_growth != 0:
                        sign = "+" if reactions_total_growth > 0 else ""
                        growth_parts.append(f"Reactions {sign}{reactions_total_growth}")
                    if comments_total_growth != 0:
                        sign = "+" if comments_total_growth > 0 else ""
                        growth_parts.append(f"Comments {sign}{comments_total_growth}")
                    if reposts_total_growth != 0:
                        sign = "+" if reposts_total_growth > 0 else ""
                        growth_parts.append(f"Reposts {sign}{reposts_total_growth}")
                    lines.append(f"[dim]Total Change: {', '.join(growth_parts)}[/dim]")
            elif engagement_history and len(engagement_history) == 1:
                # Single historical snapshot - display as simple table
                snapshot = engagement_history[0]
                lines.append("┌─────────────────┬──────────┐")
                lines.append("│ Metric          │ Count    │")
                lines.append("├─────────────────┼──────────┤")

                metrics = [
                    ("Reactions", snapshot.get("total_reactions", snapshot.get("reactions", 0))),
                    ("Comments", snapshot.get("comments", 0)),
                    ("Reposts", snapshot.get("reposts", 0)),
                ]

                if snapshot.get("views") is not None:
                    metrics.append(("Views", snapshot.get("views", 0)))

                for metric_name, value in metrics:
                    lines.append(f"│ {metric_name:<15} │ {value:>8} │")

                lines.append("└─────────────────┴──────────┘")

                date_str = snapshot.get("_downloaded_at", "")
                if date_str:
                    lines.append(f"[dim]Snapshot from: {date_str[:16]}[/dim]")
            elif engagement:
                # Display simple table from raw stats (no historical data)
                lines.append("┌─────────────────┬──────────┐")
                lines.append("│ Metric          │ Count    │")
                lines.append("├─────────────────┼──────────┤")

                # Display engagement metrics in a table format
                metrics = [
                    ("Reactions", engagement.get("total_reactions", engagement.get("reactions", engagement.get("likes", 0)))),
                    ("Comments", engagement.get("comments", 0)),
                    ("Reposts", engagement.get("reposts", engagement.get("shares", 0))),
                ]

                # Add views if available
                if engagement.get("views") is not None:
                    metrics.append(("Views", engagement.get("views", 0)))

                for metric_name, value in metrics:
                    lines.append(f"│ {metric_name:<15} │ {value:>8} │")

                lines.append("└─────────────────┴──────────┘")
                lines.append("[dim](No historical tracking data available)[/dim]")

        lines.extend([
            "",
            "[bold cyan]Text:[/bold cyan]",
            self.post_data.get("text", "No text available."),
        ])

        # Add media information
        media = self.post_data.get("media", {})
        if media and media.get("type") in ["image", "video"]:
            lines.append("")
            lines.append(f"[bold cyan]Media:[/bold cyan] {media.get('type', 'unknown').title()}")

            if media.get("type") in ["image", "images"]:
                if media.get("type") == "image" and media.get("url"):
                    lines.append(f"[dim]Image URL: {media.get('url')}[/dim]")
                elif media.get("type") == "images":
                    lines.append(f"[dim]{len(media.get('images', []))} Images[/dim]")

                if self.use_kitty_images:
                    lines.append("[yellow]Press 'i' to view image(s) in terminal[/yellow]")

        return "\n".join(lines)

    def action_dismiss(self):
        """Return to main screen."""
        self.app.pop_screen()

    def action_show_raw(self):
        """Show raw JSON data."""
        self.app.push_screen(RawJsonScreen(self.post_data))

    async def action_show_image(self):
        """Display image using Kitty graphics protocol."""
        if not self.use_kitty_images:
            self.notify("Run with --kitty-images to view images in terminal", severity="warning")
            return

        media = self.post_data.get("media", {})
        if not media:
            return

        images_to_show = []
        if media.get("type") == "image":
            url = media.get("url")
            if url:
                images_to_show.append(url)
        elif media.get("type") == "images":
            for img in media.get("images", []):
                url = img.get("url")
                if url:
                    images_to_show.append(url)

        if images_to_show:
            # Suspend the app to show image directly in terminal
            with self.app.suspend():
                for i, image_url in enumerate(images_to_show):
                    print("\n" + "="*80)
                    print(f"Displaying image {i+1}/{len(images_to_show)} (press Enter to return/continue)...")
                    print("="*80 + "\n")
                    display_image_kitty_to_terminal(image_url)
                    print("\n" + "="*80)
                    if i < len(images_to_show) - 1:
                        input("Press Enter for next image...")
                    else:
                        input("Press Enter to return to the app...")
                    print("="*80)

    def action_open_url(self):
        """Open the post URL in the default browser."""
        url = self.post_data.get("url")
        if url:
            subprocess.run(["open", url])

    def action_mark_post(self):
        """Mark/unmark the current post with 'save' action only."""
        if self.current_actions:
            # Unmark the post completely
            self.current_actions = set()
            self.update_callback(self.post_idx, None)
        else:
            # Mark with 'save' action only
            self.current_actions = {'s'}
            self.update_callback(self.post_idx, self.current_actions)

        # Update the display
        detail_widget = self.query_one("#post-detail", Static)
        detail_widget.update(self._format_post())

    def action_mark_with_actions(self):
        """Open modal to mark the current post with multiple actions."""
        def handle_actions(selected_actions):
            """Handle the selected actions from the modal."""
            if selected_actions:
                self.current_actions = selected_actions
                self.update_callback(self.post_idx, selected_actions)
            else:
                # If no actions selected, unmark the post
                self.current_actions = set()
                self.update_callback(self.post_idx, None)

            # Update the display
            detail_widget = self.query_one("#post-detail", Static)
            detail_widget.update(self._format_post())

        modal = ActionModal(self.current_actions.copy())
        self.app.push_screen(modal, handle_actions)


class TodoScreen(Screen):
    """Screen to show TODO list of marked posts."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
    ]

    def __init__(self, marked_posts_data: list):
        super().__init__()
        self.marked_posts_data = marked_posts_data

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_todos(), id="todo-list")
        )
        yield Footer()

    def _format_todos(self) -> str:
        """Format TODO list for display."""
        if not self.marked_posts_data:
            return "[yellow]No posts marked for response.[/yellow]"

        lines = [
            "[bold cyan]TODO: LinkedIn Posts to Respond To[/bold cyan]",
            "=" * 80,
            ""
        ]

        for idx, post in enumerate(self.marked_posts_data, 1):
            author = post.get("author", {})
            posted_at = post.get("posted_at", {})
            text = post.get("text", "")
            url = post.get("url", "N/A")

            # Construct name from first_name and last_name if 'name' field doesn't exist
            name = author.get('name')
            if not name:
                first_name = author.get('first_name', '')
                last_name = author.get('last_name', '')
                name = f"{first_name} {last_name}".strip() or 'N/A'

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            lines.extend([
                f"[bold yellow]({idx})[/bold yellow] Respond to post by [bold]{author.get('username', 'N/A')}[/bold]",
                f"    [cyan]Date:[/cyan] {posted_at.get('date', 'N/A')}",
                f"    [cyan]URL:[/cyan] {url}",
                f"    [cyan]Profile:[/cyan] {name} (@{author.get('username', 'N/A')})",
                f"    [cyan]Preview:[/cyan] {text_preview}",
                ""
            ])

        return "\n".join(lines)

    def action_dismiss(self):
        """Return to main screen."""
        self.app.pop_screen()


class ActionModal(Screen):
    """Modal screen for selecting multiple actions for a marked post."""

    # Define available actions with their keys and descriptions
    ACTIONS = {
        'q': {'name': 'Queue for repost', 'desc': 'Add to repost queue'},
        'a': {'name': 'Autoreact', 'desc': 'Automatically react (like, celebrate, love)'},
        'c': {'name': 'Autocomment', 'desc': 'Automatically add a comment'},
        'n': {'name': 'Manual comment', 'desc': 'Mark for manual commenting'},
        't': {'name': 'Autorepost with thoughts', 'desc': 'Automatically repost with your thoughts'},
        'r': {'name': 'Manual repost with thoughts', 'desc': 'Mark for manual repost with thoughts'},
        's': {'name': 'Save', 'desc': 'Save post for later'},
    }

    CSS = """
    ActionModal {
        align: center middle;
    }

    #action-modal-container {
        width: 80;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .action-item {
        padding: 0 1;
        margin: 0;
    }

    .action-selected {
        background: darkgreen;
        color: white;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "toggle_action('q')", show=False),
        Binding("a", "toggle_action('a')", show=False),
        Binding("c", "toggle_action('c')", show=False),
        Binding("n", "toggle_action('n')", show=False),
        Binding("t", "toggle_action('t')", show=False),
        Binding("r", "toggle_action('r')", show=False),
        Binding("s", "toggle_action('s')", show=False),
    ]

    def __init__(self, selected_actions: set = None):
        super().__init__()
        self.selected_actions = selected_actions or set()

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="action-modal-container"):
            yield Static("[bold cyan]Select Actions for Marked Post[/bold cyan]\n", id="modal-title")
            yield Static(self._format_actions(), id="action-list")
            yield Static("\n[dim]Press action key to toggle, ESC to close[/dim]", id="modal-help")

    def _format_actions(self) -> str:
        """Format the action list with current selections."""
        lines = []
        for key in ['q', 'a', 'c', 'n', 't', 'r', 's']:
            action = self.ACTIONS[key]
            is_selected = key in self.selected_actions
            checkbox = "[✓]" if is_selected else "[ ]"
            style = "bold green" if is_selected else "white"
            lines.append(f"[{style}]{checkbox} ({key}) - {action['name']}[/{style}]")
        return "\n".join(lines)

    def action_toggle_action(self, action_key: str):
        """Toggle an action on/off."""
        if action_key in self.selected_actions:
            self.selected_actions.remove(action_key)
        else:
            self.selected_actions.add(action_key)

        # Update the display
        action_list = self.query_one("#action-list", Static)
        action_list.update(self._format_actions())

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for action toggling."""
        key = event.key
        if key in self.ACTIONS:
            self.action_toggle_action(key)
            event.prevent_default()
            event.stop()

    def action_dismiss(self):
        """Close the modal and return the selected actions."""
        self.dismiss(self.selected_actions)


class MainScreen(Screen):
    """Main screen for the LinkedIn posts viewer."""

    CSS = """
    DataTable {
        height: 1fr;
    }

    #post-detail {
        padding: 1 2;
    }

    .marked {
        background: darkgreen;
    }

    #filter-input {
        dock: top;
        height: 3;
        border: solid yellow;
        display: none;
    }
    
    #status-bar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    
    #controls {
        dock: top;
        height: 3;
        align: right middle;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit_with_todos", "Quit & Show TODOs", priority=True),
        Binding("t", "view_todos", "View TODOs", priority=True),
        Binding("p", "show_profiles", "Manage Profiles"),
        Binding("m", "mark_post", "Mark Post (Save)"),
        Binding("M", "mark_with_actions", "Mark with Actions", key_display="shift+m"),
        Binding("o", "open_url", "Open URL"),
        Binding("r", "start_filter", "Filter"),
        Binding("s", "save_marked", "Save Marked"),
        Binding("n", "toggle_new_only", "Toggle New Only"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, data_source: str, use_db: bool = False, use_kitty_images: bool = False):
        super().__init__()
        self.data_source = data_source
        self.use_db = use_db
        self.use_kitty_images = use_kitty_images
        self.posts = []
        self.marked_posts = {}  # Maps post_idx to {"actions": set(), "timestamp": datetime}
        self.post_index_map = {}  # Maps row key to post index
        self.filter_active = False
        self.filter_text = ""
        self.filter_locked = False
        self._filter_timer = None
        self.show_new_only = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Input(placeholder="Type to filter posts...", id="filter-input")
        yield Static(id="status-bar")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the table when the app starts."""
        table = self.query_one(DataTable)
        table.add_column("Date", key="date")
        table.add_column("Username", key="username")
        table.add_column("Text Preview", key="text")
        table.add_column("Media", key="media")
        table.add_column("Marked", key="marked")
        table.add_column("New", key="new")

        # Show loading message
        if self.use_db:
            self.notify("Loading posts from Supabase...", timeout=30)

        self.load_and_display_posts()
        table.focus()

    def load_posts(self) -> list:
        """Load posts from DB or JSON files."""
        posts = []

        if self.use_db:
            try:
                client = get_supabase_client()

                # Get the latest import timestamp to define "new"
                latest_result = client.table('posts').select('first_seen_at').order('first_seen_at', desc=True).limit(1).execute()
                latest_import_timestamp = latest_result.data[0]['first_seen_at'] if latest_result.data else None

                # Build query
                query = client.table('posts').select('raw_json, first_seen_at, post_id')

                if self.show_new_only and latest_import_timestamp:
                    # Show all posts from the most recent import batch (within 5 minutes of latest)
                    # Calculate the cutoff timestamp
                    latest_dt = datetime.fromisoformat(latest_import_timestamp)
                    cutoff_dt = latest_dt - timedelta(minutes=5)
                    cutoff_timestamp = cutoff_dt.isoformat()

                    query = query.gte('first_seen_at', cutoff_timestamp)

                result = query.execute()
                rows = result.data

                # Optimize: Load all engagement history in one query (avoid N+1 problem)
                post_ids = [row['post_id'] for row in rows if row.get('post_id')]
                engagement_by_post = {}

                if post_ids:
                    # Batch query for all engagement history
                    history_result = client.table('data_downloads').select('post_id, downloaded_at, stats_json').in_('post_id', post_ids).order('post_id, downloaded_at').execute()

                    # Group engagement history by post_id
                    for hist_row in history_result.data:
                        post_id = hist_row['post_id']
                        if post_id not in engagement_by_post:
                            engagement_by_post[post_id] = []

                        try:
                            stats = json.loads(hist_row['stats_json'])
                            stats['_downloaded_at'] = hist_row['downloaded_at']
                            engagement_by_post[post_id].append(stats)
                        except json.JSONDecodeError:
                            continue

                # Process posts with pre-loaded engagement history
                for row in rows:
                    post = json.loads(row['raw_json'])
                    post['_first_seen_at'] = row['first_seen_at']
                    post['_post_id'] = row['post_id']

                    # Mark as new if it belongs to the latest import batch (within 5 minutes)
                    if latest_import_timestamp and row['first_seen_at']:
                        latest_dt = datetime.fromisoformat(latest_import_timestamp)
                        row_dt = datetime.fromisoformat(row['first_seen_at'])
                        post['_is_new'] = (latest_dt - row_dt) <= timedelta(minutes=5)
                    else:
                        post['_is_new'] = False

                    # Attach pre-loaded engagement history
                    if row['post_id'] and row['post_id'] in engagement_by_post:
                        post['engagement_history'] = engagement_by_post[row['post_id']]

                    posts.append(post)

                if self.show_new_only:
                    self.notify(f"Loaded {len(posts)} new posts from {latest_import_timestamp}", severity="information")
                else:
                    self.notify(f"Loaded {len(posts)} posts from Supabase", severity="information")

            except Exception as e:
                self.notify(f"Error loading from DB: {e}", severity="error")
                import traceback
                traceback.print_exc()
                return []
        else:
            # Legacy file loading
            json_files = glob.glob(f"{self.data_source}/*.json")
            for file_path in json_files:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        posts.extend(data)

        return posts

    def parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object."""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except:
            return datetime.min

    def update_status_bar(self, count: int, total: int):
        """Update the status bar with post counts."""
        status_bar = self.query_one("#status-bar", Static)
        filter_status = " (New Only)" if self.show_new_only else ""
        if self.filter_text:
            filter_status += f" (Filter: '{self.filter_text}')"
            
        status_bar.update(f"Showing {count} of {total} posts{filter_status}")

    def load_and_display_posts(self):
        """Load posts and populate the table."""
        self.posts = self.load_posts()
        total_loaded = len(self.posts)

        # Calculate date threshold (30 days ago) - only apply if NOT in "new only" mode
        # If showing new only, we want to see them regardless of age
        if not self.show_new_only:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            
            # Filter and sort posts
            filtered_posts = []
            for post in self.posts:
                date_str = post.get("posted_at", {}).get("date", "")
                datetime_obj = self.parse_date(date_str)

                if datetime_obj >= thirty_days_ago:
                    post["datetime_obj"] = datetime_obj
                    # Pre-compute searchable text for performance
                    author = post.get("author", {})
                    text = post.get("text", "")
                    username = author.get("username", "")
                    name = author.get("name", "")
                    post["_searchable"] = f"{username} {name} {text}".lower()
                    filtered_posts.append(post)
            self.posts = filtered_posts
        else:
             # For new posts, still add datetime_obj for sorting
            for post in self.posts:
                date_str = post.get("posted_at", {}).get("date", "")
                post["datetime_obj"] = self.parse_date(date_str)
                # Pre-compute searchable text
                author = post.get("author", {})
                text = post.get("text", "")
                username = author.get("username", "")
                name = author.get("name", "")
                post["_searchable"] = f"{username} {name} {text}".lower()


        # Sort by date, newest first
        self.posts.sort(key=lambda x: x.get("datetime_obj", datetime.min), reverse=True)

        # Populate table
        table = self.query_one(DataTable)
        table.clear()
        self.post_index_map.clear()
        
        for idx, post in enumerate(self.posts):
            self._add_post_to_table(idx, post, table)
            
        self.update_status_bar(len(self.posts), total_loaded)

    def on_data_table_row_selected(self, event):
        """Handle row selection (Enter key)."""
        row_key = event.row_key

        if row_key is not None and row_key in self.post_index_map:
            post_idx = self.post_index_map[row_key]
            post = self.posts[post_idx]

            # Get current actions if post is marked
            current_actions = set()
            if post_idx in self.marked_posts:
                current_actions = self.marked_posts[post_idx]["actions"].copy()

            # Create update callback
            def update_mark(idx, actions):
                self._update_post_mark(idx, actions, row_key)

            self.app.push_screen(PostDetailScreen(
                post, post_idx, current_actions, update_mark, self.use_kitty_images
            ))

    def _update_post_mark(self, post_idx: int, actions: set, row_key=None):
        """Update the mark status of a post and refresh the table if needed."""
        if actions:
            self.marked_posts[post_idx] = {
                "actions": actions,
                "timestamp": datetime.now()
            }
        elif post_idx in self.marked_posts:
            del self.marked_posts[post_idx]

        # Update table cell if we have the row_key (coming from table view)
        if row_key:
            table = self.query_one(DataTable)
            table.update_cell(row_key, "marked", self._format_actions_display(actions) if actions else "")

    def action_mark_post(self):
        """Mark/unmark the current post with 'save' action only."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        # Get all row keys and use the cursor index to find the correct one
        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.post_index_map:
                    post_idx = self.post_index_map[row_key]

                    if post_idx in self.marked_posts:
                        # Unmark the post completely
                        del self.marked_posts[post_idx]
                        table.update_cell(row_key, "marked", "")
                    else:
                        # Mark with 'save' action only
                        self.marked_posts[post_idx] = {
                            "actions": {'s'},
                            "timestamp": datetime.now()
                        }
                        table.update_cell(row_key, "marked", self._format_actions_display({'s'}))

    def _format_actions_display(self, actions: set) -> str:
        """Format action set for display in the marked column."""
        if not actions:
            return ""
        # Sort actions for consistent display (e.g., "aq" for autoreact and queue)
        return ''.join(sorted(actions))

    def action_mark_with_actions(self):
        """Open modal to mark the current post with multiple actions."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.post_index_map:
                    post_idx = self.post_index_map[row_key]

                    # Get existing actions if post is already marked
                    existing_actions = set()
                    if post_idx in self.marked_posts:
                        existing_actions = self.marked_posts[post_idx]["actions"].copy()

                    # Open the action modal with a callback
                    def handle_actions(selected_actions):
                        """Handle the selected actions from the modal."""
                        if selected_actions:
                            self.marked_posts[post_idx] = {
                                "actions": selected_actions,
                                "timestamp": datetime.now()
                            }
                            table.update_cell(row_key, "marked", self._format_actions_display(selected_actions))
                        elif post_idx in self.marked_posts:
                            # If no actions selected, unmark the post
                            del self.marked_posts[post_idx]
                            table.update_cell(row_key, "marked", "")

                    modal = ActionModal(existing_actions)
                    self.app.push_screen(modal, handle_actions)

    def action_cursor_down(self):
        """Move cursor down in the table."""
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self):
        """Move cursor up in the table."""
        table = self.query_one(DataTable)
        table.action_cursor_up()

    def action_view_todos(self):
        """Show TODO list in a popup screen."""
        marked_posts_data = [self.posts[idx] for idx in sorted(self.marked_posts.keys())]
        self.app.push_screen(TodoScreen(marked_posts_data))

    def action_show_profiles(self):
        """Show profile management screen."""
        from profile_ui import ProfileManagementScreen
        # Use the same database path as the posts
        db_path = self.data_source if self.use_db else "data/posts.db"
        self.app.push_screen(ProfileManagementScreen(db_path))

    def action_open_url(self):
        """Open the URL of the currently selected post in the default browser."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]
                if row_key in self.post_index_map:
                    post_idx = self.post_index_map[row_key]
                    post = self.posts[post_idx]
                    url = post.get("url")
                    if url:
                        subprocess.run(["open", url])

    def action_start_filter(self):
        """Start filter mode."""
        if self.filter_active:
            return

        self.filter_active = True
        self.filter_locked = False
        filter_input = self.query_one("#filter-input", Input)
        filter_input.styles.display = "block"
        filter_input.focus()
        filter_input.value = ""
        self.filter_text = ""

    def action_toggle_new_only(self):
        """Toggle showing only new posts."""
        if not self.use_db:
            self.notify("New posts filter only available with database backend", severity="warning")
            return
            
        self.show_new_only = not self.show_new_only
        status = "ON" if self.show_new_only else "OFF"
        self.notify(f"Show New Only: {status}")
        self.load_and_display_posts()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for filtering with debouncing."""
        if event.input.id == "filter-input" and self.filter_active and not self.filter_locked:
            self.filter_text = event.value

            # Stop existing timer if any
            if self._filter_timer is not None:
                self._filter_timer.stop()

            # Set a new timer to apply filter after 150ms of no typing
            self._filter_timer = self.set_timer(0.15, self.apply_filter)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle ENTER key in filter input to lock the filter."""
        if event.input.id == "filter-input" and self.filter_active:
            self.filter_locked = True
            table = self.query_one(DataTable)
            table.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for ESC to clear filter."""
        if event.key == "escape" and self.filter_active:
            # Clear the filter
            self.filter_active = False
            self.filter_locked = False
            self.filter_text = ""
            filter_input = self.query_one("#filter-input", Input)
            filter_input.styles.display = "none"
            filter_input.value = ""
            self.apply_filter()
            table = self.query_one(DataTable)
            table.focus()
            event.prevent_default()

    def action_save_marked(self):
        """Save marked posts to a JSON file with action metadata."""
        if not self.marked_posts:
            self.notify("No posts marked to save.", severity="warning")
            return

        # Collect marked posts with action metadata
        marked_posts_data = []
        for idx in sorted(self.marked_posts.keys()):
            post = self.posts[idx].copy()

            # Add action metadata to the post
            mark_info = self.marked_posts[idx]
            post["_mark_metadata"] = {
                "actions": list(mark_info["actions"]),
                "timestamp": mark_info["timestamp"].isoformat()
            }
            marked_posts_data.append(post)

        # Create export structure
        export_data = {
            "search": {
                "date": datetime.now().isoformat(),
                "query_string": self.filter_text if self.filter_active else ""
            },
            "matching_elements": marked_posts_data
        }

        # Create output directory if it doesn't exist
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"marked_posts_{timestamp}.json"

        try:
            with open(filename, 'w') as f:
                # Helper for datetime serialization if needed (though posts usually have strings)
                def json_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                json.dump(export_data, f, indent=2, default=json_serializer)
            
            self.notify(f"Saved {len(marked_posts_data)} posts to {filename}", severity="information")
            
        except Exception as e:
            self.notify(f"Error saving file: {e}", severity="error")

    def apply_filter(self):
        """Apply filter to the posts and refresh the table."""
        table = self.query_one(DataTable)
        table.clear()
        self.post_index_map.clear()

        count = 0
        if not self.filter_text:
            # No filter, show all posts
            for idx, post in enumerate(self.posts):
                self._add_post_to_table(idx, post, table)
            count = len(self.posts)
        else:
            # Use simple substring matching for speed
            filter_lower = self.filter_text.lower()

            for idx, post in enumerate(self.posts):
                searchable = post.get("_searchable", "")

                # Simple substring match (very fast)
                if filter_lower in searchable:
                    self._add_post_to_table(idx, post, table)
                    count += 1
                    
        self.update_status_bar(count, len(self.posts))

    def _add_post_to_table(self, idx: int, post: dict, table: DataTable):
        """Helper to add a post row to the table."""
        date_str = post.get("posted_at", {}).get("date", "")
        username = post.get("author", {}).get("username", "")
        text = post.get("text", "")
        text_preview = text[:50] if text else ""

        # Check if post has media
        media = post.get("media", {})
        media_indicator = ""
        if media and media.get("type") in ["image", "images", "video"]:
            images = media.get("images", [])
            if images and len(images) > 1:
                media_indicator = f"📷({len(images)})"
            else:
                media_indicator = "📷"

        # Check if post is marked and show action indicators
        if idx in self.marked_posts:
            actions = self.marked_posts[idx]["actions"]
            marked_indicator = self._format_actions_display(actions)
        else:
            marked_indicator = ""
        
        # Check if post is new
        new_indicator = "🆕" if post.get("_is_new") else ""

        row_key = table.add_row(date_str, username, text_preview, media_indicator, marked_indicator, new_indicator)
        self.post_index_map[row_key] = idx

    def action_quit_with_todos(self):
        """Print TODO list with action metadata and quit."""
        self.app.exit()

        if not self.marked_posts:
            print("\nNo posts marked for response.\n")
            return

        print("\n" + "="*80)
        print("TODO: LinkedIn Posts to Respond To")
        print("="*80 + "\n")

        # Action name mapping for display
        action_names = {
            'q': 'Queue for repost',
            'a': 'Autoreact',
            'c': 'Autocomment',
            'n': 'Manual comment',
            't': 'Autorepost with thoughts',
            'r': 'Manual repost with thoughts',
            's': 'Save'
        }

        for idx, post_idx in enumerate(sorted(self.marked_posts.keys()), 1):
            post = self.posts[post_idx]
            mark_info = self.marked_posts[post_idx]
            author = post.get("author", {})
            posted_at = post.get("posted_at", {})
            text = post.get("text", "")
            url = post.get("url", "N/A")

            # Construct name from first_name and last_name if 'name' field doesn't exist
            name = author.get('name')
            if not name:
                first_name = author.get('first_name', '')
                last_name = author.get('last_name', '')
                name = f"{first_name} {last_name}".strip() or 'N/A'

            # Format actions for display
            actions = mark_info["actions"]
            action_list = ", ".join(action_names.get(a, a) for a in sorted(actions))

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            print(f"({idx}) Actions: [{action_list}]")
            print(f"    Author: {author.get('username', 'N/A')}")
            print(f"    Date: {posted_at.get('date', 'N/A')}")
            print(f"    URL: {url}")
            print(f"    Profile: {name} (@{author.get('username', 'N/A')})")
            print(f"    Preview: {text_preview}")
            print()


class LinkedInPostsApp(App):
    """Interactive LinkedIn posts viewer application."""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, data_source: str, use_db: bool = False, use_kitty_images: bool = False):
        super().__init__()
        self.data_source = data_source
        self.use_db = use_db
        self.use_kitty_images = use_kitty_images

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.data_source, self.use_db, self.use_kitty_images))

    def compose(self) -> ComposeResult:
        # Empty compose as we push the main screen immediately
        yield from []

def main():
    """Run the application."""
    parser = argparse.ArgumentParser(
        description="Interactive LinkedIn posts viewer with marking and TODO list functionality."
    )
    parser.add_argument(
        "--no-kitty-images",
        dest="kitty_images",
        action="store_false",
        help="Disable display of images using Kitty terminal graphics"
    )
    parser.set_defaults(kitty_images=True)
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--data-dir",
        help="Directory containing LinkedIn post JSON files (legacy mode)"
    )
    group.add_argument(
        "--db",
        default="data/posts_v2.db",
        help="Path to SQLite database (default: data/posts_v2.db)"
    )

    args = parser.parse_args()
    
    # Determine mode
    if args.data_dir:
        data_source = args.data_dir
        use_db = False
    else:
        # Check if DB exists
        if Path(args.db).exists():
            data_source = args.db
            use_db = True
        else:
            # Fallback to default data dir if DB doesn't exist
            data_source = "data/20251125/linkedin"
            use_db = False
            print(f"Database not found at {args.db}, falling back to {data_source}")

    app = LinkedInPostsApp(data_source, use_db=use_db, use_kitty_images=args.kitty_images)
    app.run()


if __name__ == "__main__":
    main()
