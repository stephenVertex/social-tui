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
import asyncio
import websockets
import hashlib
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
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
LOG_FILE = LOG_DIR / "debug.log"

# Configure logging - only to file, not console (to avoid disrupting TUI)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)


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
            self.notify("Loading engagement history...", timeout=2)
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
                    'reactions': hist_row.get('reactions', 0),
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
                self.notify(f"Loaded {len(self.post_data['engagement_history'])} engagement snapshots", severity="information")

        except Exception as e:
            logger.error(f"Error lazy loading engagement for {post_id}: {e}")
            self.notify(f"Error loading engagement: {e}", severity="error")

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
            f"[bold cyan]Author:[/bold cyan] {author.get('username', 'N/A')}",
            f"[bold cyan]Name:[/bold cyan] {name}",
            f"[bold cyan]URL:[/bold cyan] {self.post_data.get('url', 'N/A')}",
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
            lines.append("[bold cyan]Engagement:[/bold cyan]")

            # Case 1: More than one snapshot, show historical trend
            if len(engagement_history) > 1:
                current = engagement_history[-1]
                previous = engagement_history[-2]

                # Display historical timeline table
                lines.append("")
                lines.append("[bold]Historical Timeline:[/bold]")
                lines.append("┌─────────────────────┬────────────┬──────────┬──────────┐")
                lines.append("│ Date                │ Reactions  │ Comments │ Reposts  │")
                lines.append("├─────────────────────┼────────────┼──────────┼──────────┤")

                display_history = engagement_history[-10:]
                for snapshot in display_history:
                    date_str = snapshot.get("_downloaded_at", "")
                    try:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        date_display = dt.strftime("%b %d %H:%M")
                    except:
                        date_display = date_str[:16] if len(date_str) > 16 else date_str

                    reactions = snapshot.get("reactions", 0)
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

                metric_keys = [("Reactions", "reactions"), ("Comments", "comments"), ("Reposts", "reposts")]
                if current.get("views") is not None:
                    metric_keys.append(("Views", "views"))

                for metric_name, key in metric_keys:
                    current_val = current.get(key, 0)
                    prev_val = previous.get(key, 0)
                    change = current_val - prev_val
                    change_str = f"+{change}" if change > 0 else str(change)
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
                    ("Reactions", snapshot.get("reactions", 0)),
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
        
        else:
            # Case 3: No engagement history at all
            lines.append("")
            lines.append("[bold cyan]Engagement:[/bold cyan]")
            lines.append("[dim]No engagement data available.[/dim]")

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


class RunHistoryScreen(Screen):
    """Screen to show download run history."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "show_stats", "Stats"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, project_id: str = None):
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
            client = get_supabase_client()

            # Use Supabase RPC function to execute custom SQL
            # This assumes an RPC function exists, or we do it via table queries
            result = client.table('download_runs').select(
                'run_id, started_at, completed_at, status, script_name, platform, '
                'posts_fetched, posts_new, posts_updated, error_message, system_info'
            ).order('started_at', desc=True).execute()

            # Manually calculate snapshot counts for each run
            self.runs = []
            for run in result.data:
                snapshot_result = client.table('data_downloads').select(
                    'download_id, post_id', count='exact'
                ).eq('run_id', run['run_id']).execute()

                run['snapshot_count'] = snapshot_result.count or 0
                # Get unique post count
                unique_posts = set()
                for item in snapshot_result.data:
                    if item.get('post_id'):
                        unique_posts.add(item['post_id'])
                run['unique_posts_tracked'] = len(unique_posts)

                # Calculate duration
                if run['completed_at'] and run['started_at']:
                    try:
                        started = datetime.fromisoformat(run['started_at'].replace('Z', '+00:00'))
                        completed = datetime.fromisoformat(run['completed_at'].replace('Z', '+00:00'))
                        run['duration_seconds'] = (completed - started).total_seconds()
                    except:
                        run['duration_seconds'] = None
                else:
                    run['duration_seconds'] = None

                self.runs.append(run)

            # Calculate summary statistics
            total = len(self.runs)
            completed = sum(1 for r in self.runs if r['status'] == 'completed')
            failed = sum(1 for r in self.runs if r['status'] == 'failed')
            avg_posts = sum(r['posts_fetched'] or 0 for r in self.runs) / total if total > 0 else 0

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
            logger.error(f"Error loading runs: {e}")
            import traceback
            traceback.print_exc()

    def _add_run_to_table(self, run: dict, table: DataTable):
        """Add a single run to the table."""
        # Format datetime
        started_at = run.get('started_at', '')
        if started_at:
            try:
                dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                dt_str = started_at[:19] if len(started_at) > 19 else started_at
        else:
            dt_str = "N/A"

        # Format status with emoji
        status_map = {
            'completed': '✓ Done',
            'failed': '✗ Failed',
            'running': '⟳ Running'
        }
        status = status_map.get(run.get('status'), run.get('status', 'N/A'))

        # Format duration
        duration = self._format_duration(run.get('duration_seconds'))

        table.add_row(
            dt_str,
            status,
            str(run.get('posts_fetched', 0)),
            str(run.get('posts_new', 0)),
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

    def action_cursor_down(self):
        """Move cursor down."""
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self):
        """Move cursor up."""
        table = self.query_one(DataTable)
        table.action_cursor_up()

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
        started_at = run.get('started_at', '')
        completed_at = run.get('completed_at', '')

        started = None
        completed = None

        if started_at:
            try:
                started = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            except:
                pass

        if completed_at:
            try:
                completed = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            except:
                pass

        # Calculate stats
        duration_seconds = run.get('duration_seconds', 0) or 0
        posts_fetched = run.get('posts_fetched', 0) or 0
        posts_per_sec = posts_fetched / duration_seconds if duration_seconds > 0 else 0
        sec_per_post = duration_seconds / posts_fetched if posts_fetched > 0 else 0
        new_pct = (run.get('posts_new', 0) / posts_fetched * 100) if posts_fetched > 0 else 0

        lines = [
            f"[bold cyan]Run ID:[/bold cyan] {run.get('run_id', 'N/A')}",
        ]

        if started:
            lines.append(f"[bold cyan]Started:[/bold cyan] {started.strftime('%Y-%m-%d %H:%M:%S')} UTC")

        if completed:
            lines.append(f"[bold cyan]Completed:[/bold cyan] {completed.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            lines.append(f"[bold cyan]Duration:[/bold cyan] {self._format_duration(duration_seconds)}")

        status_display = {
            'completed': '✓ Completed',
            'failed': '✗ Failed',
            'running': '⟳ Running'
        }.get(run.get('status'), run.get('status', 'Unknown'))

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
        run_id = self.run_data.get('run_id')
        if not run_id:
            self.notify("No run ID available", severity="warning")
            return

        try:
            subprocess.run(
                ['pbcopy'],
                input=run_id.encode('utf-8'),
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

    def __init__(self, project_id: str = None):
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
            client = get_supabase_client()

            # Fetch all runs to calculate statistics
            all_runs_result = client.table('download_runs').select(
                'run_id, started_at, completed_at, status, platform, posts_fetched, posts_new'
            ).execute()

            all_runs = all_runs_result.data
            total_runs = len(all_runs)

            # Calculate statistics manually
            stats = {
                'total_runs': total_runs,
                'completed_runs': sum(1 for r in all_runs if r.get('status') == 'completed'),
                'failed_runs': sum(1 for r in all_runs if r.get('status') == 'failed'),
                'running_runs': sum(1 for r in all_runs if r.get('status') == 'running'),
                'total_posts_fetched': sum(r.get('posts_fetched', 0) or 0 for r in all_runs),
                'total_new_posts': sum(r.get('posts_new', 0) or 0 for r in all_runs),
                'avg_posts_per_run': sum(r.get('posts_fetched', 0) or 0 for r in all_runs) / total_runs if total_runs > 0 else 0,
                'max_posts_in_run': max((r.get('posts_fetched', 0) or 0 for r in all_runs), default=0),
                'min_posts_in_run': min((r.get('posts_fetched', 0) or 0 for r in all_runs if r.get('posts_fetched')), default=0),
            }

            # Calculate duration statistics
            durations = []
            for r in all_runs:
                if r.get('completed_at') and r.get('started_at'):
                    try:
                        started = datetime.fromisoformat(r['started_at'].replace('Z', '+00:00'))
                        completed = datetime.fromisoformat(r['completed_at'].replace('Z', '+00:00'))
                        durations.append((completed - started).total_seconds())
                    except:
                        pass

            stats['avg_duration_seconds'] = sum(durations) / len(durations) if durations else 0
            stats['max_duration_seconds'] = max(durations) if durations else 0
            stats['min_duration_seconds'] = min(durations) if durations else 0

            # Find last run and last success
            sorted_runs = sorted(all_runs, key=lambda r: r.get('started_at', ''), reverse=True)
            stats['last_run_at'] = sorted_runs[0].get('started_at') if sorted_runs else None

            completed_runs = [r for r in sorted_runs if r.get('status') == 'completed']
            stats['last_success_at'] = completed_runs[0].get('started_at') if completed_runs else None

            # Calculate runs in last 24h and 7d
            now = datetime.now(timezone.utc)
            day_ago = now - timedelta(hours=24)
            week_ago = now - timedelta(days=7)

            stats['runs_24h'] = sum(1 for r in all_runs if r.get('started_at') and
                                   datetime.fromisoformat(r['started_at'].replace('Z', '+00:00')) > day_ago)
            stats['runs_7d'] = sum(1 for r in all_runs if r.get('started_at') and
                                  datetime.fromisoformat(r['started_at'].replace('Z', '+00:00')) > week_ago)

            # Calculate platform breakdown
            platform_counts = {}
            platform_posts = {}
            for r in all_runs:
                platform = r.get('platform', 'unknown')
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
                platform_posts[platform] = platform_posts.get(platform, 0) + (r.get('posts_fetched', 0) or 0)

            platforms = [{'platform': p, 'run_count': platform_counts[p], 'total_posts': platform_posts[p]}
                        for p in platform_counts]
            platforms.sort(key=lambda x: x['run_count'], reverse=True)

            display = self.query_one("#statistics", Static)
            display.update(self._format_statistics(stats, platforms))
        except Exception as e:
            self.notify(f"Error loading statistics: {e}", severity="error")
            logger.error(f"Error loading statistics: {e}")

    def _format_statistics(self, stats: dict = None, platforms: list = None) -> str:
        """Format statistics for display."""
        if not stats:
            return "Loading statistics..."

        # Calculate percentages
        total = stats.get('total_runs', 0)
        success_pct = (stats.get('completed_runs', 0) / total * 100) if total > 0 else 0
        fail_pct = (stats.get('failed_runs', 0) / total * 100) if total > 0 else 0

        # Format last run time
        last_run = "Never"
        last_run_at = stats.get('last_run_at')
        if last_run_at:
            try:
                last_run_dt = datetime.fromisoformat(last_run_at.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                delta = now - last_run_dt
                last_run = self._format_relative_time(delta)
            except:
                last_run = str(last_run_at)[:19]

        lines = [
            "[bold]Overall Performance:[/bold]",
            f"  Total Runs:           {stats.get('total_runs', 0)}",
            f"  Successful:           {stats.get('completed_runs', 0)} ({success_pct:.1f}%)",
            f"  Failed:               {stats.get('failed_runs', 0)} ({fail_pct:.1f}%)",
            f"  Currently Running:    {stats.get('running_runs', 0)}",
            "",
            "[bold]Post Collection:[/bold]",
            f"  Total Posts Fetched:  {stats.get('total_posts_fetched', 0):,} posts",
            f"  Total New Posts:      {stats.get('total_new_posts', 0):,} posts",
            f"  Average per Run:      {stats.get('avg_posts_per_run', 0):.0f} posts",
            f"  Max in Single Run:    {stats.get('max_posts_in_run', 0)} posts",
            f"  Min in Single Run:    {stats.get('min_posts_in_run', 0)} posts",
            "",
        ]

        if platforms:
            lines.append("[bold]Platform Breakdown:[/bold]")
            for p in platforms:
                pct = (p['run_count'] / total * 100) if total > 0 else 0
                platform_name = p.get('platform', 'unknown').title()
                lines.append(f"  {platform_name:<15} {p['run_count']} runs ({pct:.0f}%)")
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

    #filter-options-popup {
        dock: top;
        height: auto;
        width: 60;
        background: $surface-darken-1;
        border: thick $accent;
        padding: 1 2;
        display: none; /* Initially hidden */
        color: $text;
        text-align: left;
        margin-left: 2;
        margin-top: 1;
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
        Binding("h", "show_run_history", "Run History"),
        Binding("m", "mark_post", "Mark Post (Save)"),
        Binding("M", "mark_with_actions", "Mark with Actions", key_display="shift+m"),
        Binding("o", "open_url", "Open URL"),
        Binding("r", "start_filter", "Filter"),
        Binding("s", "save_marked", "Save Marked"),
        Binding("n", "toggle_new_only", "Toggle New Only"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, data_source: str, use_db: bool = False, use_kitty_images: bool = False, websocket_port: int = None):
        super().__init__()
        self.data_source = data_source
        self.use_db = use_db
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
        self.prefix_mode_active = False # New: Tracks if C-u prefix mode is active
        self.current_filter_type = None # New: Stores the type of filter being applied (e.g., 'username', 'platform', 'content')

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Input(placeholder="Type to filter posts...", id="filter-input")
        yield Static(id="filter-options-popup", markup=True)
        yield Static(id="status-bar")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the table when the app starts."""
        table = self.query_one(DataTable)
        table.add_column("Date", key="date")
        table.add_column("Username", key="username")
        table.add_column("Platform", key="platform")
        table.add_column("Text Preview", key="text")
        table.add_column("Media", key="media")
        table.add_column("Marked", key="marked")
        table.add_column("New", key="new")

        self.load_and_display_posts()
        table.focus()

    def load_posts(self, verbose: bool = True) -> list:
        """Load posts from DB or JSON files.

        Args:
            verbose: If True, show detailed progress notifications. If False, only show final result.
        """
        posts = []

        if self.use_db:
            try:
                client = get_supabase_client()

                # Get the latest import timestamp to define "new"
                if verbose:
                    self.notify("Checking for latest posts...", timeout=5)
                latest_result = client.table('posts').select('first_seen_at').order('first_seen_at', desc=True).limit(1).execute()
                latest_import_timestamp = latest_result.data[0]['first_seen_at'] if latest_result.data else None

                # Build query for main posts data from the new view
                main_posts_query = client.table('v_main_post_view').select('*')

                if self.show_new_only and latest_import_timestamp:
                    latest_dt = datetime.fromisoformat(latest_import_timestamp)
                    cutoff_dt = latest_dt - timedelta(minutes=5)
                    cutoff_timestamp = cutoff_dt.isoformat()
                    main_posts_query = main_posts_query.gte('first_seen_at', cutoff_timestamp)

                if verbose:
                    self.notify("Loading posts from Supabase view...", timeout=10)
                main_posts_result = main_posts_query.execute()
                main_posts_data = main_posts_result.data
                
                # Fetch raw_json separately for post detail screen, keyed by post_id
                raw_json_map = {}
                if main_posts_data:
                    post_ids_for_raw_json = [row['post_id'] for row in main_posts_data]
                    raw_json_result = client.table('posts').select('post_id, raw_json').in_('post_id', post_ids_for_raw_json).execute()
                    for row in raw_json_result.data:
                        raw_json_map[row['post_id']] = row['raw_json']

                if verbose:
                    self.notify(f"Loaded {len(main_posts_data)} main posts, now loading engagement history...", timeout=10)

                # Smart engagement loading: prefetch recent posts (last 15 days), lazy load old posts
                post_ids = [row['post_id'] for row in main_posts_data if row.get('post_id')]
                engagement_by_post = {}

                logger.info("="*60)
                logger.info("Starting smart engagement history load for main view")
                logger.info(f"Total posts loaded for main view: {len(main_posts_data)}")
                logger.info(f"Total post_ids extracted: {len(post_ids)}")

                # Separate recent posts (last 15 days) from older posts
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=15)
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
                            # If parsing fails, treat as old (will be lazy loaded)
                            old_post_ids.append(post_id)
                    else:
                        old_post_ids.append(post_id)

                logger.info(f"Recent posts (last 15 days): {len(recent_post_ids)}")
                logger.info(f"Older posts (lazy load): {len(old_post_ids)}")
                logger.info("="*60)

                # Only prefetch engagement for recent posts
                if recent_post_ids:
                    if verbose:
                        self.notify(f"Loading engagement history for {len(recent_post_ids)} recent posts...", timeout=10)

                    # Fetch with a reasonable limit (recent posts won't have many snapshots)
                    # Estimate ~5 snapshots per recent post max
                    limit = len(recent_post_ids) * 5
                    history_result = client.table('v_post_engagement_history').select(
                        'post_id, downloaded_at, reactions, comments, reposts, views, download_id'
                    ).in_('post_id', recent_post_ids).limit(limit).execute()

                    logger.info(f"Query to post_engagement_history returned {len(history_result.data)} rows for recent posts")

                    # Group engagement history by post_id
                    if verbose:
                        self.notify(f"Processing {len(history_result.data)} engagement snapshots...", timeout=5)
                    for hist_row in history_result.data:
                        post_id = hist_row['post_id']
                        if post_id not in engagement_by_post:
                            engagement_by_post[post_id] = []

                        # Data from the view is already parsed and cleaned
                        stats = {
                            'reactions': hist_row.get('reactions', 0),
                            'comments': hist_row.get('comments', 0),
                            'reposts': hist_row.get('reposts', 0),
                            'views': hist_row.get('views'),
                            '_downloaded_at': hist_row.get('downloaded_at'),
                            'download_id': hist_row.get('download_id')
                        }
                        engagement_by_post[post_id].append(stats)

                # Process posts with pre-loaded engagement history
                if verbose:
                    self.notify(f"Processing {len(main_posts_data)} posts...", timeout=5)
                for row in main_posts_data:
                    # Use raw_json_map to get the full post data
                    post = json.loads(raw_json_map.get(row['post_id'], '{}'))
                    post['first_seen_at'] = row['first_seen_at']
                    post['post_id'] = row['post_id']
                    post['text_preview'] = row['text_preview']
                    post['media_indicator'] = row['media_indicator']
                    post['marked_indicator'] = row['marked_indicator']
                    post['posted_at_formatted'] = row['posted_at_formatted'] # Add formatted date for table
                    post['author_username'] = row['author_username']
                    post['platform'] = row['platform'] # Add platform for table

                    # Mark as new if it belongs to the latest import batch (within 5 minutes)
                    if latest_import_timestamp and row['first_seen_at']:
                        latest_dt = datetime.fromisoformat(latest_import_timestamp)
                        row_dt = datetime.fromisoformat(row['first_seen_at'])
                        post['_is_new'] = (latest_dt - row_dt) <= timedelta(minutes=5)
                    else:
                        post['_is_new'] = False

                    # Attach pre-loaded engagement history (for recent posts)
                    # For older posts, mark for lazy loading
                    if row['post_id'] and row['post_id'] in engagement_by_post:
                        # Sort the engagement history by timestamp to ensure correct order
                        sorted_history = sorted(engagement_by_post[row['post_id']], key=lambda x: x['_downloaded_at'])

                        # Include the virtual 'zero point' for visualization
                        post['engagement_history'] = sorted_history
                        post['_engagement_loaded'] = True
                    else:
                        # Mark as not loaded - will be fetched on demand when viewing post detail
                        post['engagement_history'] = []
                        post['_engagement_loaded'] = False

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


    def update_status_bar(self, count: int, total: int):
        """Update the status bar with post counts."""
        status_bar = self.query_one("#status-bar", Static)
        filter_status = " (New Only)" if self.show_new_only else ""
        if self.filter_active and self.filter_text:
            if self.current_filter_type == "username":
                filter_status += f" (User: '{self.filter_text}')"
            elif self.current_filter_type == "platform":
                filter_status += f" (Platform: '{self.filter_text}')"
            elif self.current_filter_type == "min_date":
                filter_status += f" (Min Date: '{self.filter_text}')"
            elif self.current_filter_type == "max_date":
                filter_status += f" (Max Date: '{self.filter_text}')"
            elif self.current_filter_type == "min_engagements":
                filter_status += f" (Min Engagements: '{self.filter_text}')"
            else: # Default content filter
                filter_status += f" (Filter: '{self.filter_text}')"
            
        status_bar.update(f"Showing {count} of {total} posts{filter_status}")

    def load_and_display_posts(self, verbose: bool = True):
        """Load posts and populate the table.

        Args:
            verbose: If True, show detailed progress notifications. If False, only show final result.
        """
        self.posts = self.load_posts(verbose=verbose)
        total_loaded = len(self.posts)



        # Sort by date, newest first (already handled by view, but good for consistency)
        self.posts.sort(key=lambda x: datetime.fromisoformat(x.get('posted_at_formatted').replace(' ', 'T')), reverse=True)

        # Populate table
        table = self.query_one(DataTable)
        table.clear()
        self.post_index_map.clear()
        
        for idx, post in enumerate(self.posts):
            # Use pre-formatted data from the view
            date_str = post.get("posted_at_formatted", "")
            username = post.get("author_username", "")
            text_preview = post.get("text_preview", "")
            media_indicator = post.get("media_indicator", "")
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
        """Update the mark status of a post and refresh the table if needed."""
        if actions:
            self.marked_posts[post_idx] = {
                "actions": actions,
                "timestamp": datetime.now(timezone.utc)
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
                            "timestamp": datetime.now(timezone.utc)
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
                                "timestamp": datetime.now(timezone.utc)
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

    def action_show_run_history(self):
        """Show run history screen."""
        if not self.use_db:
            self.notify("Run history only available with database backend", severity="warning")
            return

        self.app.push_screen(RunHistoryScreen())

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

        # Ensure the filter options popup is hidden when regular filter mode starts
        filter_options_popup = self.query_one("#filter-options-popup", Static)
        filter_options_popup.styles.display = "none"

    def action_toggle_new_only(self):
        """Toggle showing only new posts."""
        if not self.use_db:
            self.notify("New posts filter only available with database backend", severity="warning")
            return

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
        """Handle key events for ESC to clear filter, and C-u for filter prefixes."""
        filter_options_popup = self.query_one("#filter-options-popup", Static)
        filter_input = self.query_one("#filter-input", Input)

        if event.key == "ctrl+u":
            self.prefix_mode_active = True
            # Display the filter options popup
            menu_text = """
[bold]Filter options:[/bold]
 u - username (fuzzy match)
 p - platform (e.g., linkedin, substack)
 c - content (full text search)
 d - min date (YYYY-MM-DD)
 D - max date (YYYY-MM-DD)
 r - min engagements (number)
 [dim](ESC to cancel)[/dim]
            """
            filter_options_popup.update(menu_text.strip())
            filter_options_popup.styles.display = "block"
            # self.notify("Prefix mode active. Enter filter type (u, p, c, d, D, r)...", severity="information", timeout=3)
            event.prevent_default()
            event.stop()
        elif self.prefix_mode_active:
            # filter_input = self.query_one("#filter-input", Input)
            filter_options_popup.styles.display = "none" # Hide popup after a key is pressed

            if event.key == "u":
                self.current_filter_type = "username"
                filter_input.placeholder = "Filter by username (fuzzy match)..."
                self.notify("Username filter active. Type username.", severity="information", timeout=2)
            elif event.key == "p":
                self.current_filter_type = "platform"
                filter_input.placeholder = "Filter by platform (e.g., linkedin, youtube)..."
                self.notify("Platform filter active. Type platform.", severity="information", timeout=2)
            elif event.key == "c":
                self.current_filter_type = "content"
                filter_input.placeholder = "Filter by content (full text search)..."
                self.notify("Content filter active. Type content.", severity="information", timeout=2)
            elif event.key == "d":
                self.current_filter_type = "min_date"
                filter_input.placeholder = "Filter by minimum date (YYYY-MM-DD)..."
                self.notify("Minimum date filter active. Type date.", severity="information", timeout=2)
            elif event.key == "D":
                self.current_filter_type = "max_date"
                filter_input.placeholder = "Filter by maximum date (YYYY-MM-DD)..."
                self.notify("Maximum date filter active. Type date.", severity="information", timeout=2)
            elif event.key == "r":
                self.current_filter_type = "min_engagements"
                filter_input.placeholder = "Filter by minimum engagements (number)..."
                self.notify("Minimum engagements filter active. Type number.", severity="information", timeout=2)
            elif event.key == "escape": # Allow escape to cancel prefix mode
                self.prefix_mode_active = False
                self.current_filter_type = None
                self.notify("Prefix mode cancelled.", severity="information", timeout=2)
                filter_input.placeholder = "Type to filter posts..." # Reset placeholder
                event.prevent_default()
                event.stop()
                return # Don't start filter if prefix mode is cancelled with escape

            self.prefix_mode_active = False # Exit prefix mode after a valid key
            self.action_start_filter() # Activate the filter input with the new placeholder
            event.prevent_default()
            event.stop()
        elif event.key == "escape" and self.filter_active:
            # Clear the filter
            self.filter_active = False
            self.filter_locked = False
            self.filter_text = ""
            self.current_filter_type = None # Also clear the filter type
            # filter_input = self.query_one("#filter-input", Input)
            filter_input.styles.display = "none"
            filter_input.value = ""
            filter_input.placeholder = "Type to filter posts..." # Reset placeholder
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
                "date": datetime.now(timezone.utc).isoformat(),
                "query_string": self.filter_text if self.filter_active else ""
            },
            "matching_elements": marked_posts_data
        }

        # Create output directory if it doesn't exist
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)

        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
            filter_lower = self.filter_text.lower()

            for idx, post in enumerate(self.posts):
                filter_match = False # Assume no match initially

                if self.current_filter_type == "username":
                    username = post.get("author_username", "").lower()
                    if filter_lower in username:
                        filter_match = True
                elif self.current_filter_type == "platform":
                    platform = post.get("platform", "").lower()
                    if filter_lower in platform:
                        filter_match = True
                elif self.current_filter_type == "min_date":
                    try:
                        # Convert filter text to datetime object
                        filter_date = datetime.strptime(self.filter_text, "%Y-%m-%d")
                        post_date_str = post.get("posted_at_formatted", "")
                        if post_date_str:
                            # Parse post date, ignore time for min_date comparison
                            post_date = datetime.strptime(post_date_str.split(" ")[0], "%Y-%m-%d")
                            if post_date >= filter_date:
                                filter_match = True
                    except ValueError:
                        self.notify(f"Invalid min date format: {self.filter_text}. Use YYYY-MM-DD.", severity="error")
                        # If date is invalid, no posts match this filter until corrected
                        continue 
                elif self.current_filter_type == "max_date":
                    try:
                        filter_date = datetime.strptime(self.filter_text, "%Y-%m-%d")
                        post_date_str = post.get("posted_at_formatted", "")
                        if post_date_str:
                            post_date = datetime.strptime(post_date_str.split(" ")[0], "%Y-%m-%d")
                            if post_date <= filter_date:
                                filter_match = True
                    except ValueError:
                        self.notify(f"Invalid max date format: {self.filter_text}. Use YYYY-MM-DD.", severity="error")
                        continue
                elif self.current_filter_type == "min_engagements":
                    try:
                        min_engagements = int(self.filter_text)
                        # Sum reactions, comments, reposts from the latest snapshot
                        engagement_history = post.get("engagement_history", [])
                        if engagement_history:
                            latest_snapshot = engagement_history[-1]
                            total_engagements = (
                                latest_snapshot.get("reactions", 0) +
                                latest_snapshot.get("comments", 0) +
                                latest_snapshot.get("reposts", 0)
                            )
                            if total_engagements >= min_engagements:
                                filter_match = True
                        elif min_engagements == 0: # If no engagement history, it matches if min_engagements is 0
                            filter_match = True
                    except ValueError:
                        self.notify(f"Invalid minimum engagements number: {self.filter_text}. Enter an integer.", severity="error")
                        continue
                else: # Default content filter or if current_filter_type is not recognized/None
                    searchable = post.get("_searchable", "")
                    if filter_lower in searchable:
                        filter_match = True

                if filter_match:
                    self._add_post_to_table(idx, post, table)
                    count += 1
                    
        self.update_status_bar(count, len(self.posts))

    def _add_post_to_table(self, idx: int, post: dict, table: DataTable):
        """Helper to add a single post to the DataTable."""
        date_str = post.get("posted_at_formatted", "")
        username = post.get("author_username", "")
        platform = post.get("platform", "") # Get platform
        text_preview = post.get("text_preview", "")
        media_indicator = post.get("media_indicator", "")
        marked_indicator = post.get("marked_indicator", "")
        new_indicator = "🆕" if post.get("_is_new") else ""

        row_key = table.add_row(date_str, username, platform, text_preview, media_indicator, marked_indicator, new_indicator)
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

    def __init__(self, data_source: str, use_db: bool = False, use_kitty_images: bool = False, websocket_port: int = None):
        super().__init__()
        self.data_source = data_source
        self.use_db = use_db
        self.use_kitty_images = use_kitty_images
        self.websocket_port = websocket_port

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.data_source, self.use_db, self.use_kitty_images, self.websocket_port))

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
    
    parser.add_argument(
        "--websocket-port",
        type=int,
        help="Port for the websocket server for external visualization"
    )

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

    app = LinkedInPostsApp(
        data_source, 
        use_db=use_db, 
        use_kitty_images=args.kitty_images,
        websocket_port=args.websocket_port
    )
    app.run()


if __name__ == "__main__":
    main()
