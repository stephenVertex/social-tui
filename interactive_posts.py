#!/usr/bin/env python3
"""
Interactive LinkedIn posts viewer with marking and TODO list functionality.
"""

import json
import glob
import argparse
import base64
import sys
from pathlib import Path
from datetime import datetime, timedelta
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static
from textual.containers import Container, VerticalScroll
from textual.binding import Binding
from textual.screen import Screen


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

            # Download image to temp file
            parsed = urlparse(image_url)
            if parsed.scheme in ('http', 'https'):
                print(f"Downloading image...")
                with urlopen(image_url, timeout=10) as response:
                    image_data = response.read()
            else:
                with open(image_url, 'rb') as f:
                    image_data = f.read()

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
        parsed = urlparse(image_url)
        if parsed.scheme in ('http', 'https'):
            print(f"Downloading image (using graphics protocol)...")
            with urlopen(image_url, timeout=10) as response:
                image_data = response.read()
        else:
            with open(image_url, 'rb') as f:
                image_data = f.read()

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


class LinkedInPostsApp(App):
    """Interactive LinkedIn posts viewer application."""

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
    """

    BINDINGS = [
        Binding("q", "quit_with_todos", "Quit & Show TODOs", priority=True),
        Binding("t", "view_todos", "View TODOs", priority=True),
        Binding("m", "mark_post", "Mark Post"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, data_dir: str, use_kitty_images: bool = False):
        super().__init__()
        self.data_dir = data_dir
        self.use_kitty_images = use_kitty_images
        self.posts = []
        self.marked_posts = set()
        self.post_index_map = {}  # Maps row key to post index

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
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
                filtered_posts.append(post)

        # Sort by date, newest first
        filtered_posts.sort(key=lambda x: x.get("datetime_obj", datetime.min), reverse=True)
        self.posts = filtered_posts

        # Populate table
        table = self.query_one(DataTable)
        for idx, post in enumerate(self.posts):
            date_str = post.get("posted_at", {}).get("date", "")
            username = post.get("author", {}).get("username", "")
            text = post.get("text", "")
            text_preview = text[:50] if text else ""

            # Check if post has media
            media = post.get("media", {})
            has_media = "📷" if media and media.get("type") in ["image", "video"] else ""

            row_key = table.add_row(date_str, username, text_preview, has_media, "")
            self.post_index_map[row_key] = idx

    def on_data_table_row_selected(self, event):
        """Handle row selection (Enter key)."""
        row_key = event.row_key

        if row_key is not None and row_key in self.post_index_map:
            post_idx = self.post_index_map[row_key]
            post = self.posts[post_idx]
            self.push_screen(PostDetailScreen(post, self.use_kitty_images))

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

    def action_view_todos(self):
        """Show TODO list in a popup screen."""
        marked_posts_data = [self.posts[idx] for idx in sorted(self.marked_posts)]
        self.push_screen(TodoScreen(marked_posts_data))

    def action_quit_with_todos(self):
        """Print TODO list and quit."""
        self.exit()

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
