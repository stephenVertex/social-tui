#!/usr/bin/env python3
"""
Interactive YouTube video viewer with marking and TODO list functionality.
Adapted from interactive_posts.py for YouTube content.
"""

import json
import glob
import argparse
import base64
import sys
import asyncio
import websockets
import hashlib
import subprocess
import logging
import uuid
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

# Setup debug logging
LOG_DIR = Path("log")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "youtube_debug.log"

# Configure logging - only to file, not console (to avoid disrupting TUI)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)


# Action type mapping
ACTION_TYPE_MAP = {
    'w': 'watch_later',
    's': 'save',
    'n': 'note',
    'a': 'auto_summarize_and_post',
    'k': 'add_to_knowledge_base',
    'i': 'add_to_inspiration_sources'
}
REVERSE_ACTION_TYPE_MAP = {v: k for k, v in ACTION_TYPE_MAP.items()}


def sync_actions_to_db(post_id: str, added_actions: set, removed_actions: set):
    """Sync action changes to Supabase."""
    try:
        client = get_supabase_client()
        
        # Handle additions
        for action_key in added_actions:
            action_type = ACTION_TYPE_MAP.get(action_key)
            if action_type:
                try:
                    # Check if already exists to avoid duplicates (though not unique constrained, it's cleaner)
                    # For simplicity in this TUI, we just insert. The UUID ensures no PK collision.
                    client.table('action_queue').insert({
                        'action_id': str(uuid.uuid4()),
                        'post_id': post_id,
                        'action_type': action_type,
                        'status': 'pending',
                        'created_at': datetime.now().isoformat()
                    }).execute()
                    logger.info(f"Added action {action_type} for {post_id}")
                except Exception as e:
                    logger.error(f"Error adding action {action_type} for {post_id}: {e}")

        # Handle removals
        for action_key in removed_actions:
            action_type = ACTION_TYPE_MAP.get(action_key)
            if action_type:
                try:
                    client.table('action_queue').delete().eq('post_id', post_id).eq('action_type', action_type).execute()
                    logger.info(f"Removed action {action_type} for {post_id}")
                except Exception as e:
                    logger.error(f"Error removing action {action_type} for {post_id}: {e}")
                    
    except Exception as e:
        logger.error(f"Error in sync_actions_to_db: {e}")


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
        # print(f"Using cached image: {cache_path.name}")
        with open(cache_path, 'rb') as f:
            return f.read()

    # Download and cache
    # print(f"Downloading image...")
    image_data = download_image(image_url)

    # Save to cache
    with open(cache_path, 'wb') as f:
        f.write(image_data)
    # print(f"Cached image: {cache_path.name}")

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
                sys.stdout.buffer.write(f"\033_Ga=T,f=100;{chunk}\033".encode('ascii'))
            elif i == len(chunks) - 1:
                sys.stdout.buffer.write(f"\033_Gm=0;{chunk}\033".encode('ascii'))
            else:
                sys.stdout.buffer.write(f"\033_Gm=1;{chunk}\033".encode('ascii'))

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
        Binding("i", "show_image", "View Thumbnail"),
        Binding("o", "open_url", "Open Video"),
        Binding("u", "copy_urn", "Copy URN"),
        Binding("m", "mark_post", "Mark Post (Save)"),
        Binding("M", "mark_with_actions", "Mark with Actions", key_display="shift+m"),
    ]

    def __init__(self, post_data: dict, post_idx: int, current_actions: set,
                 update_callback, use_kitty_images: bool = False, websocket_port: int = None):
        super().__init__()
        self.post_data = post_data
        self.post_idx = post_idx
        self.current_actions = current_actions
        self.update_callback = update_callback
        self.use_kitty_images = use_kitty_images
        self.websocket_port = websocket_port

    def on_mount(self) -> None:
        """Send post data to websocket on screen mount and lazy load engagement if needed."""
        # Lazy load engagement history if not already loaded
        if not self.post_data.get('_engagement_loaded', True):
            self.app.run_worker(self.lazy_load_engagement, thread=True)

        if self.websocket_port:
            self.app.run_worker(self.send_to_websocket, thread=True)

    async def lazy_load_engagement(self):
        """Lazy load engagement history for this post on demand."""
        post_id = self.post_data.get('post_id')
        if not post_id:
            return

        try:
            self.notify("Loading statistics history...", timeout=2)
            from supabase_client import get_supabase_client
            client = get_supabase_client()

            # Fetch engagement history for this specific post
            history_result = client.table('v_post_engagement_history').select(
                'post_id, downloaded_at, reactions, comments, reposts, views, download_id'
            ).eq('post_id', post_id).execute()

            # Process and attach engagement history
            engagement_history = []
            for hist_row in history_result.data:
                stats = {
                    'reactions': hist_row.get('reactions', 0), # Likes
                    'comments': hist_row.get('comments', 0),
                    'reposts': hist_row.get('reposts', 0),
                    'views': hist_row.get('views'),
                    '_downloaded_at': hist_row.get('downloaded_at'),
                    'download_id': hist_row.get('download_id')
                }
                engagement_history.append(stats)

            # Sort and include virtual initial point for visualization
            sorted_history = sorted(engagement_history, key=lambda x: x['_downloaded_at'])
            self.post_data['engagement_history'] = sorted_history
            self.post_data['_engagement_loaded'] = True

            # Refresh the display
            detail_widget = self.query_one("#post-detail", Static)
            detail_widget.update(self._format_post())

            if len(self.post_data['engagement_history']) > 0:
                self.notify(f"Loaded {len(self.post_data['engagement_history'])} stats snapshots", severity="information")

        except Exception as e:
            logger.error(f"Error lazy loading engagement for {post_id}: {e}")
            self.notify(f"Error loading stats: {e}", severity="error")

    async def send_to_websocket(self):
        """Send post data to the websocket server."""
        if not self.websocket_port:
            return
        
        uri = f"ws://127.0.0.1:{self.websocket_port}"
        try:
            # Use a short timeout for connecting
            async with websockets.connect(uri, open_timeout=1) as websocket:
                
                def json_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    # Add this to handle Path objects if they appear
                    if isinstance(obj, Path):
                        return str(obj)
                    raise TypeError(f"Type {type(obj)} not serializable")
                
                payload = json.dumps({
                    "type": "post_detail",
                    "data": self.post_data
                }, default=json_serializer)
                
                await websocket.send(payload)
                self.notify(f"Sent post to visualizer")
        except (OSError, asyncio.TimeoutError):
            self.notify(f"Visualizer not connected on port {self.websocket_port}", severity="warning", timeout=5)
        except Exception as e:
            self.notify(f"Websocket error: {e}", severity="error")

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
            f"[bold cyan]Channel:[/bold cyan] {author.get('username', 'N/A')}",
            f"[bold cyan]Video URL:[/bold cyan] {self.post_data.get('url', 'N/A')}",
        ]

        # Add URN if available
        urn = self.post_data.get('full_urn')
        if urn:
            lines.append(f"[bold cyan]Full URN:[/bold cyan] {urn}")
            lines.append("[dim]Press 'u' to copy URN to clipboard[/dim]")

        # Add post_id if available (for debugging)
        post_id = self.post_data.get('post_id')
        if post_id:
            lines.append(f"[bold cyan]Post ID:[/bold cyan] [dim]{post_id}[/dim]")

        # Add marked status
        if self.current_actions:
            actions_display = ''.join(sorted(self.current_actions))
            lines.append(f"[bold cyan]Marked:[/bold cyan] [bold green]{actions_display}[/bold green]")
        else:
            lines.append(f"[bold cyan]Marked:[/bold cyan] No")

        # Add engagement data if available
        engagement_history = self.post_data.get("engagement_history", [])

        if engagement_history:
            lines.append("")
            lines.append("[bold cyan]Statistics:[/bold cyan]")

            # Case 1: More than one snapshot, show historical trend
            if len(engagement_history) > 1:
                current = engagement_history[-1]
                previous = engagement_history[-2]

                # Display historical timeline table
                lines.append("")
                lines.append("[bold]Historical Timeline:[/bold]")
                lines.append("┌─────────────────────┬────────────┬──────────┬──────────┐")
                lines.append("│ Date                │ Likes      │ Comments │ Views    │")
                lines.append("├─────────────────────┼────────────┼──────────┼──────────┤")

                display_history = engagement_history[-10:]
                for snapshot in display_history:
                    date_str = snapshot.get("_downloaded_at", "")
                    try:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        date_display = dt.strftime("%b %d %H:%M")
                    except:
                        date_display = date_str[:16] if len(date_str) > 16 else date_str

                    reactions = snapshot.get("reactions", 0) # Likes
                    comments = snapshot.get("comments", 0)
                    views = snapshot.get("views", 0)
                    lines.append(f"│ {date_display:<19} │ {reactions:>10} │ {comments:>8} │ {views:>8} │")

                lines.append("└─────────────────────┴────────────┴──────────┴──────────┘")

                # Display summary with trend
                lines.append("")
                lines.append("[bold]Summary:[/bold]")
                lines.append("┌─────────────────┬──────────┬──────────┬────────────┐")
                lines.append("│ Metric          │ Current  │ Change   │ Trend      │")
                lines.append("├─────────────────┼──────────┼──────────┼────────────┤")

                # Note: 'reactions' maps to Likes for YouTube
                metric_keys = [("Likes", "reactions"), ("Comments", "comments")]
                if current.get("views") is not None:
                    metric_keys.append(("Views", "views"))

                for metric_name, key in metric_keys:
                    current_val = current.get(key, 0)
                    prev_val = previous.get(key, 0)
                    change = current_val - prev_val
                    change_str = f"{'+{change}'}" if change > 0 else str(change)
                    trend = "↗" if change > 0 else ("↘" if change < 0 else "→")
                    lines.append(f"│ {metric_name:<15} │ {current_val:>8} │ {change_str:>8} │ {trend:<10} │")

                lines.append("└─────────────────┴──────────┴──────────┴────────────┘")

                # Show time range and total change
                first_snapshot = engagement_history[0]
                last_snapshot = engagement_history[-1]
                try:
                    first_dt = datetime.fromisoformat(first_snapshot.get("_downloaded_at", "").replace('Z', '+00:00'))
                    last_dt = datetime.fromisoformat(last_snapshot.get("_downloaded_at", "").replace('Z', '+00:00'))
                    days_elapsed = (last_dt - first_dt).total_seconds() / 86400
                    time_range = f"{first_dt.strftime('%b %d')} → {last_dt.strftime('%b %d %H:%M')}"
                    lines.append(f"[dim]Tracked: {time_range} ({len(engagement_history)} snapshots over {days_elapsed:.1f} days)[/dim]")
                except:
                    lines.append(f"[dim]Tracked: {len(engagement_history)} snapshots[/dim]")

            # Case 2: Exactly one snapshot, show a simple table
            elif len(engagement_history) == 1:
                snapshot = engagement_history[0]
                lines.append("┌─────────────────┬──────────┐")
                lines.append("│ Metric          │ Count    │")
                lines.append("├─────────────────┼──────────┤")

                metrics = [
                    ("Likes", snapshot.get("reactions", 0)),
                    ("Comments", snapshot.get("comments", 0)),
                ]
                if snapshot.get("views") is not None:
                    metrics.append(("Views", snapshot.get("views", 0)))

                for metric_name, value in metrics:
                    lines.append(f"│ {metric_name:<15} │ {value:>8} │")

                lines.append("└─────────────────┴──────────┘")
                date_str = snapshot.get("_downloaded_at", "")
                if date_str:
                    lines.append(f"[dim]Snapshot from: {date_str[:16]}[/dim]")
        
        else:
            # Case 3: No engagement history at all
            lines.append("")
            lines.append("[bold cyan]Statistics:[/bold cyan]")
            lines.append("[dim]No statistics available.[/dim]")

        lines.extend([
            "",
            "[bold cyan]Description:[/bold cyan]",
            self.post_data.get("text", "No description available."),
        ])

        # Add media information
        media = self.post_data.get("media", {})
        if media and media.get("type") in ["video"]:
            lines.append("")
            lines.append(f"[bold cyan]Thumbnail:[/bold cyan] Available")
            lines.append(f"[dim]Thumbnail URL: {media.get('local_file_path') or media.get('url')}[/dim]")
            
            if self.use_kitty_images:
                lines.append("[yellow]Press 'i' to view thumbnail in terminal[/yellow]")

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
        
        image_url = None
        # In YouTube fetcher, we stored thumbnail URL in local_file_path
        if media.get("type") == "video":
            image_url = media.get("local_file_path") or media.get("url")

        if image_url:
            # Suspend the app to show image directly in terminal
            with self.app.suspend():
                print("\n" + "="*80)
                print(f"Displaying thumbnail (press Enter to return)...")
                print("="*80 + "\n")
                display_image_kitty_to_terminal(image_url)
                print("\n" + "="*80)
                input("Press Enter to return to the app...")
                print("="*80)

    def action_open_url(self):
        """Open the post URL in the default browser."""
        url = self.post_data.get("url")
        if url:
            subprocess.run(["open", url])

    def action_copy_urn(self):
        """Copy the full URN to clipboard."""
        urn = self.post_data.get("full_urn")
        if not urn:
            self.notify("No URN available for this post", severity="warning")
            return

        try:
            # Use pbcopy on macOS to copy to clipboard
            process = subprocess.run(
                ['pbcopy'],
                input=urn.encode('utf-8'),
                check=True
            )
            self.notify(f"URN copied to clipboard!", severity="information")
        except Exception as e:
            self.notify(f"Error copying to clipboard: {e}", severity="error")

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
            return "[yellow]No videos marked for action.[/yellow]"

        lines = [
            "[bold cyan]TODO: YouTube Videos to Process[/bold cyan]",
            "=" * 80,
            ""
        ]

        for idx, post in enumerate(self.marked_posts_data, 1):
            author = post.get("author", {})
            posted_at = post.get("posted_at", {})
            text = post.get("text", "")
            url = post.get("url", "N/A")

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            lines.extend([
                f"[bold yellow]({idx})[/bold yellow] Video by [bold]{author.get('username', 'N/A')}[/bold]",
                f"    [cyan]Date:[/cyan] {posted_at.get('date', 'N/A')}",
                f"    [cyan]URL:[/cyan] {url}",
                f"    [cyan]Channel:[/cyan] @{author.get('username', 'N/A')}",
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
        'w': {'name': 'Watch Later', 'desc': 'Mark to watch later'},
        's': {'name': 'Save/Archive', 'desc': 'Save for reference'},
        'n': {'name': 'Note', 'desc': 'Add to notes'},
        'a': {'name': 'Auto-Summarize & Post', 'desc': 'Generate summary and draft social post'},
        'k': {'name': 'Add to Knowledge Base', 'desc': 'Add video content to knowledge base'},
        'i': {'name': 'Add to Inspiration Sources', 'desc': 'Add video to inspiration sources'},
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
        Binding("w", "toggle_action('w')", show=False),
        Binding("s", "toggle_action('s')", show=False),
        Binding("n", "toggle_action('n')", show=False),
        Binding("a", "toggle_action('a')", show=False),
        Binding("k", "toggle_action('k')", show=False),
        Binding("i", "toggle_action('i')", show=False),
    ]

    def __init__(self, selected_actions: set = None):
        super().__init__()
        self.selected_actions = selected_actions or set()

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="action-modal-container"):
            yield Static("[bold cyan]Select Actions for Video[/bold cyan]\n", id="modal-title")
            yield Static(self._format_actions(), id="action-list")
            yield Static("\n[dim]Press action key to toggle, ESC to close[/dim]", id="modal-help")

    def _format_actions(self) -> str:
        """Format the action list with current selections."""
        lines = []
        for key in ['w', 's', 'n', 'a', 'k', 'i']:
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
    """Main screen for the YouTube posts viewer."""

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
        Binding("o", "open_url", "Open Video"),
        Binding("r", "start_filter", "Filter"),
        Binding("s", "save_marked", "Save Marked"),
        Binding("n", "toggle_new_only", "Toggle New Only"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, use_kitty_images: bool = False, websocket_port: int = None):
        super().__init__()
        self.use_kitty_images = use_kitty_images
        self.websocket_port = websocket_port
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
        yield Input(placeholder="Type to filter videos...", id="filter-input")
        yield Static(id="status-bar")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the table when the app starts."""
        table = self.query_one(DataTable)
        table.add_column("Date", key="date")
        table.add_column("Channel", key="username")
        table.add_column("Title/Description", key="text")
        table.add_column("Media", key="media")
        table.add_column("Marked", key="marked")
        table.add_column("New", key="new")

        self.load_and_display_posts()
        table.focus()

    def load_posts(self, verbose: bool = True) -> list:
        """Load posts from DB.

        Args:
            verbose: If True, show detailed progress notifications. If False, only show final result.
        """
        posts = []

        try:
            client = get_supabase_client()

            # Get the latest import timestamp to define "new"
            if verbose:
                self.notify("Checking for latest YouTube videos...", timeout=5)
            
            # Filter for youtube platform
            latest_result = client.table('posts') \
                .select('first_seen_at') \
                .eq('platform', 'youtube') \
                .order('first_seen_at', desc=True) \
                .limit(1).execute()
                
            latest_import_timestamp = latest_result.data[0]['first_seen_at'] if latest_result.data else None

            # Build query for main posts data from the new view
            main_posts_query = client.table('v_main_post_view').select('*').eq('platform', 'youtube')

            if self.show_new_only and latest_import_timestamp:
                latest_dt = datetime.fromisoformat(latest_import_timestamp)
                cutoff_dt = latest_dt - timedelta(minutes=5)
                cutoff_timestamp = cutoff_dt.isoformat()
                main_posts_query = main_posts_query.gte('first_seen_at', cutoff_timestamp)

            if verbose:
                self.notify("Loading videos from Supabase view...", timeout=10)
            main_posts_result = main_posts_query.execute()
            main_posts_data = main_posts_result.data
            
            # Fetch raw_json separately for post detail screen, keyed by post_id
            raw_json_map = {}
            post_media_map = {}
            if main_posts_data:
                post_ids_for_raw_json = [row['post_id'] for row in main_posts_data]
                
                # Fetch raw_json
                raw_json_result = client.table('posts').select('post_id, raw_json').in_('post_id', post_ids_for_raw_json).execute()
                for row in raw_json_result.data:
                    raw_json_map[row['post_id']] = row['raw_json']
                    
                # Fetch media info (thumbnails)
                media_result = client.table('post_media').select('post_id, media_type, media_url, local_file_path').in_('post_id', post_ids_for_raw_json).execute()
                for row in media_result.data:
                    pid = row['post_id']
                    if pid not in post_media_map:
                        post_media_map[pid] = {'type': 'video', 'url': None, 'local_file_path': None}
                    
                    # If we find an image (thumbnail), prefer its local path
                    if row['media_type'] == 'image':
                        post_media_map[pid]['local_file_path'] = row['local_file_path']
                        # If we don't have a main URL yet, use this (though usually video has the main URL)
                    
                    # If we find the video record, use its URL as the main media URL
                    if row['media_type'] == 'video':
                        post_media_map[pid]['url'] = row['media_url']
                        post_media_map[pid]['type'] = 'video'

            if verbose:
                self.notify(f"Loaded {len(main_posts_data)} videos, now loading stats...", timeout=10)

            # Smart engagement loading: prefetch recent posts (last 15 days), lazy load old posts
            post_ids = [row['post_id'] for row in main_posts_data if row.get('post_id')]
            engagement_by_post = {}

            logger.info("="*60)
            logger.info("Starting smart engagement history load for main view (YouTube)")
            logger.info(f"Total posts loaded for main view: {len(main_posts_data)}")
            
            # Separate recent posts (last 15 days) from older posts
            cutoff_date = datetime.now() - timedelta(days=15)
            recent_post_ids = []
            old_post_ids = []

            for row in main_posts_data:
                post_id = row.get('post_id')
                if not post_id:
                    continue

                # Use posted_at_formatted to determine post age (actual post date, not import date)
                posted_at = row.get('posted_at_formatted')
                if posted_at:
                    try:
                        # posted_at_formatted is like "2025-11-30 22:56:19"
                        posted_at_dt = datetime.strptime(posted_at, "%Y-%m-%d %H:%M:%S")
                        if posted_at_dt >= cutoff_date:
                            recent_post_ids.append(post_id)
                        else:
                            old_post_ids.append(post_id)
                    except:
                        old_post_ids.append(post_id)
                else:
                    old_post_ids.append(post_id)

            # Only prefetch engagement for recent posts
            if recent_post_ids:
                if verbose:
                    self.notify(f"Loading stats for {len(recent_post_ids)} recent videos...", timeout=10)

                # Fetch with a reasonable limit
                limit = len(recent_post_ids) * 5
                history_result = client.table('v_post_engagement_history').select(
                    'post_id, downloaded_at, reactions, comments, reposts, views, download_id'
                ).in_('post_id', recent_post_ids).limit(limit).execute()

                # Group engagement history by post_id
                if verbose:
                    self.notify(f"Processing {len(history_result.data)} stats snapshots...", timeout=5)
                for hist_row in history_result.data:
                    post_id = hist_row['post_id']
                    if post_id not in engagement_by_post:
                        engagement_by_post[post_id] = []

                    stats = {
                        'reactions': hist_row.get('reactions', 0), # Likes
                        'comments': hist_row.get('comments', 0),
                        'reposts': hist_row.get('reposts', 0),
                        'views': hist_row.get('views'),
                        '_downloaded_at': hist_row.get('downloaded_at'),
                        'download_id': hist_row.get('download_id')
                    }
                    engagement_by_post[post_id].append(stats)

            # Process posts with pre-loaded engagement history
            if verbose:
                self.notify(f"Processing {len(main_posts_data)} videos...", timeout=5)
            for row in main_posts_data:
                # Use raw_json_map to get the full post data
                post = json.loads(raw_json_map.get(row['post_id'], '{}'))
                post['first_seen_at'] = row['first_seen_at']
                post['post_id'] = row['post_id']
                post['text_preview'] = row['text_preview']
                post['media_indicator'] = "Video" # Always video for YouTube
                post['marked_indicator'] = row['marked_indicator']
                post['posted_at_formatted'] = row['posted_at_formatted'] # Add formatted date for table
                post['author_username'] = row['author_username']
                
                # Ensure we have the full URL if not in raw_json
                if 'url' not in post:
                     post['url'] = f"https://www.youtube.com/watch?v={row['urn']}"
                
                # Add full URN
                post['full_urn'] = f"youtube:video:{row['urn']}"

                # Inject media info from our manual fetch
                if row['post_id'] in post_media_map:
                    post['media'] = post_media_map[row['post_id']]
                else:
                    # Fallback if no media record found (shouldn't happen for new fetcher)
                    post['media'] = {
                        'type': 'video',
                        'url': post['url'],
                        'local_file_path': None
                    }

                # Mark as new if it belongs to the latest import batch (within 5 minutes)
                if latest_import_timestamp and row['first_seen_at']:
                    latest_dt = datetime.fromisoformat(latest_import_timestamp)
                    row_dt = datetime.fromisoformat(row['first_seen_at'])
                    post['_is_new'] = (latest_dt - row_dt) <= timedelta(minutes=5)
                else:
                    post['_is_new'] = False

                # Attach pre-loaded engagement history (for recent posts)
                if row['post_id'] and row['post_id'] in engagement_by_post:
                    sorted_history = sorted(engagement_by_post[row['post_id']], key=lambda x: x['_downloaded_at'])
                    post['engagement_history'] = sorted_history
                    post['_engagement_loaded'] = True
                else:
                    post['engagement_history'] = []
                    post['_engagement_loaded'] = False

                posts.append(post)

            # Fetch actions from action_queue and attach to posts
            if posts:
                if verbose:
                    self.notify("Loading actions from queue...", timeout=5)
                
                post_ids = [p['post_id'] for p in posts if p.get('post_id')]
                actions_map = {} 
                
                if post_ids:
                    try:
                        # Fetch actions for these posts
                        actions_result = client.table('action_queue').select('post_id, action_type').in_('post_id', post_ids).neq('status', 'completed').execute()
                        
                        for action_row in actions_result.data:
                            pid = action_row['post_id']
                            atype = action_row['action_type']
                            akey = REVERSE_ACTION_TYPE_MAP.get(atype)
                            
                            if pid and akey:
                                if pid not in actions_map:
                                    actions_map[pid] = set()
                                actions_map[pid].add(akey)
                    except Exception as e:
                        logger.error(f"Error fetching actions from DB: {e}")
                            
                # Attach actions to posts
                for post in posts:
                    pid = post.get('post_id')
                    if pid and pid in actions_map:
                        post['_db_actions'] = actions_map[pid]
                        post['marked_indicator'] = ''.join(sorted(actions_map[pid]))
                    else:
                        post['_db_actions'] = set()
                        post['marked_indicator'] = ""

            if self.show_new_only:
                self.notify(f"Loaded {len(posts)} new videos from {latest_import_timestamp}", severity="information")
            else:
                self.notify(f"Loaded {len(posts)} videos from Supabase", severity="information")

        except Exception as e:
            self.notify(f"Error loading from DB: {e}", severity="error")
            import traceback
            traceback.print_exc()
            return []

        return posts


    def update_status_bar(self, count: int, total: int):
        """Update the status bar with post counts."""
        status_bar = self.query_one("#status-bar", Static)
        filter_status = " (New Only)" if self.show_new_only else ""
        if self.filter_text:
            filter_status += f" (Filter: '{self.filter_text}')"
            
        status_bar.update(f"Showing {count} of {total} videos{filter_status}")

    def load_and_display_posts(self, verbose: bool = True):
        """Load posts and populate the table.

        Args:
            verbose: If True, show detailed progress notifications. If False, only show final result.
        """
        self.posts = self.load_posts(verbose=verbose)
        total_loaded = len(self.posts)

        # Sort by date, newest first
        self.posts.sort(key=lambda x: datetime.fromisoformat(x.get('posted_at_formatted').replace(' ', 'T')), reverse=True)

        # Populate table
        table = self.query_one(DataTable)
        table.clear()
        self.post_index_map.clear()
        self.marked_posts.clear()
        
        for idx, post in enumerate(self.posts):
            # Restore marks from DB
            if post.get('_db_actions'):
                self.marked_posts[idx] = {
                    "actions": post['_db_actions'],
                    "timestamp": datetime.now()
                }
            date_str = post.get("posted_at_formatted", "")
            username = post.get("author_username", "")
            text_preview = post.get("text_preview", "")
            media_indicator = "Video"
            marked_indicator = post.get("marked_indicator", "")
            new_indicator = "🆕" if post.get("_is_new") else ""

            row_key = table.add_row(date_str, username, text_preview, media_indicator, marked_indicator, new_indicator)
            self.post_index_map[row_key] = idx
            
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
                post, post_idx, current_actions, update_mark, self.use_kitty_images, self.websocket_port
            ))

    def _update_post_mark(self, post_idx: int, actions: set, row_key=None):
        """Update the mark status of a post, sync to DB, and refresh the table if needed."""
        post = self.posts[post_idx]
        post_id = post.get('post_id')
        
        # Calculate diffs
        old_actions = set()
        if post_idx in self.marked_posts:
            old_actions = self.marked_posts[post_idx]["actions"]
            
        new_actions = actions if actions else set()
        
        added = new_actions - old_actions
        removed = old_actions - new_actions
        
        # Sync to DB in background
        if (added or removed) and post_id:
            self.app.run_worker(lambda: sync_actions_to_db(post_id, added, removed), thread=True)

        # Update local state
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

                    # Toggle behavior: if marked at all, unmark completely. Else mark with 's'.
                    if post_idx in self.marked_posts:
                        self._update_post_mark(post_idx, None, row_key)
                    else:
                        self._update_post_mark(post_idx, {'s'}, row_key)

    def _format_actions_display(self, actions: set) -> str:
        """Format action set for display in the marked column."""
        if not actions:
            return ""
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
                        self._update_post_mark(post_idx, selected_actions, row_key)

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
        self.app.push_screen(ProfileManagementScreen("data/posts.db")) # dummy path as it uses supabase

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
        self.show_new_only = not self.show_new_only
        status = "ON" if self.show_new_only else "OFF"
        self.notify(f"Show New Only: {status}", timeout=2)
        self.load_and_display_posts(verbose=False)

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
        filename = output_dir / f"marked_youtube_videos_{timestamp}.json"

        try:
            with open(filename, 'w') as f:
                # Helper for datetime serialization
                def json_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")

                json.dump(export_data, f, indent=2, default=json_serializer)
            
            self.notify(f"Saved {len(marked_posts_data)} videos to {filename}", severity="information")
            
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
                # Search in text and author
                searchable = (post.get("text", "") + " " + post.get("author_username", "")).lower()

                # Simple substring match
                if filter_lower in searchable:
                    self._add_post_to_table(idx, post, table)
                    count += 1
                    
        self.update_status_bar(count, len(self.posts))
        
    def _add_post_to_table(self, idx: int, post: dict, table: DataTable):
        """Helper to add a single post row to the table."""
        date_str = post.get("posted_at_formatted", "")
        username = post.get("author_username", "")
        text_preview = post.get("text_preview", "")
        media_indicator = "Video"
        marked_indicator = post.get("marked_indicator", "")
        new_indicator = "🆕" if post.get("_is_new") else ""

        row_key = table.add_row(date_str, username, text_preview, media_indicator, marked_indicator, new_indicator)
        self.post_index_map[row_key] = idx


    def action_quit_with_todos(self):
        """Print TODO list with action metadata and quit."""
        self.app.exit()

        if not self.marked_posts:
            print("\nNo videos marked for action.\n")
            return

        print("\n" + "="*80)
        print("TODO: YouTube Videos to Process")
        print("="*80 + "\n")

        # Action name mapping for display
        action_names = {
            'w': 'Watch Later',
            's': 'Save/Archive',
            'n': 'Note',
            'a': 'Auto-Summarize & Post',
            'k': 'Add to Knowledge Base',
            'i': 'Add to Inspiration Sources',
        }

        for idx, post_idx in enumerate(sorted(self.marked_posts.keys()), 1):
            post = self.posts[post_idx]
            mark_info = self.marked_posts[post_idx]
            author = post.get("author", {})
            posted_at = post.get("posted_at", {})
            text = post.get("text", "")
            url = post.get("url", "N/A")

            # Format actions for display
            actions = mark_info["actions"]
            action_list = ", ".join(action_names.get(a, a) for a in sorted(actions))

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            print(f"({idx}) Actions: [{action_list}]")
            print(f"    Channel: @{author.get('username', 'N/A')}")
            print(f"    Date: {posted_at.get('date', 'N/A')}")
            print(f"    URL: {url}")
            print(f"    Title/Desc: {text_preview}")
            print()


class YouTubeViewerApp(App):
    """Interactive YouTube video viewer application."""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, use_kitty_images: bool = False, websocket_port: int = None):
        super().__init__()
        self.use_kitty_images = use_kitty_images
        self.websocket_port = websocket_port

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.use_kitty_images, self.websocket_port))

    def compose(self) -> ComposeResult:
        # Empty compose as we push the main screen immediately
        yield from []

def main():
    """Run the application."""
    parser = argparse.ArgumentParser(
        description="Interactive YouTube video viewer with marking and TODO list functionality."
    )
    parser.add_argument(
        "--no-kitty-images",
        dest="kitty_images",
        action="store_false",
        help="Disable display of thumbnails using Kitty terminal graphics"
    )
    parser.set_defaults(kitty_images=True)
    
    parser.add_argument(
        "--websocket-port",
        type=int,
        help="Port for the websocket server for external visualization"
    )

    args = parser.parse_args()
    
    app = YouTubeViewerApp(
        use_kitty_images=args.kitty_images,
        websocket_port=args.websocket_port
    )
    app.run()


if __name__ == "__main__":
    main()