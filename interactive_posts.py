#!/usr/bin/env python3
"""
Interactive LinkedIn posts viewer with marking and TODO list functionality.
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
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static, Input
from textual.containers import Container, VerticalScroll
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
    ]

    def __init__(self, post_data: dict):
        super().__init__()
        self.post_data = post_data

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            Static(self._format_json(), id="raw-json")
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


class PostDetailScreen(Screen):
    """Screen to show full post details."""

    BINDINGS = [
        Binding("escape", "dismiss", "Back", priority=True),
        Binding("r", "show_raw", "Raw JSON"),
        Binding("i", "show_image", "View Image"),
        Binding("o", "open_url", "Open URL"),
    ]

    def __init__(self, post_data: dict, use_kitty_images: bool = False):
        super().__init__()
        self.post_data = post_data
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

        lines = [
            f"[bold cyan]Date:[/bold cyan] {posted_at.get('date', 'N/A')}",
            f"[bold cyan]Author:[/bold cyan] {author.get('username', 'N/A')}",
            f"[bold cyan]Name:[/bold cyan] {author.get('name', 'N/A')}",
            f"[bold cyan]URL:[/bold cyan] {self.post_data.get('url', 'N/A')}",
            "",
            "[bold cyan]Text:[/bold cyan]",
            self.post_data.get("text", "No text available."),
        ]

        # Add media information
        media = self.post_data.get("media", {})
        if media and media.get("type") in ["image", "video"]:
            lines.append("")
            lines.append(f"[bold cyan]Media:[/bold cyan] {media.get('type', 'unknown').title()}")

            if media.get("type") == "image" and media.get("url"):
                lines.append(f"[dim]Image URL: {media.get('url')}[/dim]")
                if self.use_kitty_images:
                    lines.append("[yellow]Press 'i' to view image in terminal[/yellow]")

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
            return

        media = self.post_data.get("media", {})
        if media and media.get("type") == "image":
            image_url = media.get("url")
            if image_url:
                # Suspend the app to show image directly in terminal
                with self.app.suspend():
                    print("\n" + "="*80)
                    print("Displaying image (press Enter to return)...")
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

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            lines.extend([
                f"[bold yellow]({idx})[/bold yellow] Respond to post by [bold]{author.get('username', 'N/A')}[/bold]",
                f"    [cyan]Date:[/cyan] {posted_at.get('date', 'N/A')}",
                f"    [cyan]URL:[/cyan] {url}",
                f"    [cyan]Profile:[/cyan] {author.get('name', 'N/A')} (@{author.get('username', 'N/A')})",
                f"    [cyan]Preview:[/cyan] {text_preview}",
                ""
            ])

        return "\n".join(lines)

    def action_dismiss(self):
        """Return to main screen."""
        self.app.pop_screen()


class MainScreen(Screen):
    """Main screen for the LinkedIn posts viewer."""

    CSS = """
    DataTable {
        height: 100%;
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
    """

    BINDINGS = [
        Binding("q", "quit_with_todos", "Quit & Show TODOs", priority=True),
        Binding("t", "view_todos", "View TODOs", priority=True),
        Binding("m", "mark_post", "Mark Post"),
        Binding("o", "open_url", "Open URL"),
        Binding("r", "start_filter", "Filter"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, data_dir: str, use_kitty_images: bool = False):
        super().__init__()
        self.data_dir = data_dir
        self.use_kitty_images = use_kitty_images
        self.posts = []
        self.marked_posts = set()
        self.post_index_map = {}  # Maps row key to post index
        self.filter_active = False
        self.filter_text = ""
        self.filter_locked = False
        self._filter_timer = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Input(placeholder="Type to filter posts...", id="filter-input")
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

        self.load_and_display_posts()
        table.focus()

    def load_posts(self) -> list:
        """Load all posts from JSON files in the specified directory."""
        posts = []
        json_files = glob.glob(f"{self.data_dir}/*.json")

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

    def load_and_display_posts(self):
        """Load posts and populate the table."""
        self.posts = self.load_posts()

        # Calculate date threshold (30 days ago)
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

        # Sort by date, newest first
        filtered_posts.sort(key=lambda x: x.get("datetime_obj", datetime.min), reverse=True)
        self.posts = filtered_posts

        # Populate table
        table = self.query_one(DataTable)
        for idx, post in enumerate(self.posts):
            self._add_post_to_table(idx, post, table)

    def on_data_table_row_selected(self, event):
        """Handle row selection (Enter key)."""
        row_key = event.row_key

        if row_key is not None and row_key in self.post_index_map:
            post_idx = self.post_index_map[row_key]
            post = self.posts[post_idx]
            self.app.push_screen(PostDetailScreen(post, self.use_kitty_images))

    def action_mark_post(self):
        """Mark/unmark the current post."""
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
                        self.marked_posts.remove(post_idx)
                        table.update_cell(row_key, "marked", "")
                    else:
                        self.marked_posts.add(post_idx)
                        table.update_cell(row_key, "marked", "✅")

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
        marked_posts_data = [self.posts[idx] for idx in sorted(self.marked_posts)]
        self.app.push_screen(TodoScreen(marked_posts_data))

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

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for filtering with debouncing."""
        if event.input.id == "filter-input" and self.filter_active and not self.filter_locked:
            self.filter_text = event.value

            # Stop existing timer if any
            if self._filter_timer is not None and self._filter_timer.is_running:
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

    def apply_filter(self):
        """Apply filter to the posts and refresh the table."""
        table = self.query_one(DataTable)
        table.clear()
        self.post_index_map.clear()

        if not self.filter_text:
            # No filter, show all posts
            for idx, post in enumerate(self.posts):
                self._add_post_to_table(idx, post, table)
        else:
            # Use simple substring matching for speed
            filter_lower = self.filter_text.lower()

            for idx, post in enumerate(self.posts):
                searchable = post.get("_searchable", "")

                # Simple substring match (very fast)
                if filter_lower in searchable:
                    self._add_post_to_table(idx, post, table)

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

        # Check if post is marked
        marked_indicator = "✅" if idx in self.marked_posts else ""

        row_key = table.add_row(date_str, username, text_preview, media_indicator, marked_indicator)
        self.post_index_map[row_key] = idx

    def action_quit_with_todos(self):
        """Print TODO list and quit."""
        self.app.exit()

        if not self.marked_posts:
            print("\nNo posts marked for response.\n")
            return

        print("\n" + "="*80)
        print("TODO: LinkedIn Posts to Respond To")
        print("="*80 + "\n")

        for idx, post_idx in enumerate(sorted(self.marked_posts), 1):
            post = self.posts[post_idx]
            author = post.get("author", {})
            posted_at = post.get("posted_at", {})
            text = post.get("text", "")
            url = post.get("url", "N/A")

            # Truncate text for preview
            text_preview = text[:100] + "..." if len(text) > 100 else text

            print(f"({idx}) Respond to post by {author.get('username', 'N/A')}")
            print(f"    Date: {posted_at.get('date', 'N/A')}")
            print(f"    URL: {url}")
            print(f"    Profile: {author.get('name', 'N/A')} (@{author.get('username', 'N/A')})")
            print(f"    Preview: {text_preview}")
            print()


class LinkedInPostsApp(App):
    """Interactive LinkedIn posts viewer application."""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, data_dir: str, use_kitty_images: bool = False):
        super().__init__()
        self.data_dir = data_dir
        self.use_kitty_images = use_kitty_images

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.data_dir, self.use_kitty_images))

    def compose(self) -> ComposeResult:
        # Empty compose as we push the main screen immediately
        yield from []

def main():
    """Run the application."""
    parser = argparse.ArgumentParser(
        description="Interactive LinkedIn posts viewer with marking and TODO list functionality."
    )
    parser.add_argument(
        "--kitty-images",
        action="store_true",
        help="Display images using Kitty terminal graphics (requires Kitty terminal and 'icat' command)"
    )
    parser.add_argument(
        "--data-dir",
        default="data/20251125/linkedin",
        help="Directory containing LinkedIn post JSON files (default: data/20251125/linkedin)"
    )

    args = parser.parse_args()

    app = LinkedInPostsApp(args.data_dir, use_kitty_images=args.kitty_images)
    app.run()


if __name__ == "__main__":
    main()
