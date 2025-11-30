"""Profile management UI for social-tui."""

from textual.app import ComposeResult
from textual.widgets import DataTable, Footer, Header, Static, Input, Button, Label
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.binding import Binding
from textual.screen import Screen
from textual import events
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
import subprocess
import re

from profile_manager import ProfileManager
from tag_manager import TagManager


class AddProfileModal(Screen):
    """Modal screen for adding a new profile."""

    CSS = """
    AddProfileModal {
        align: center middle;
    }

    #add-profile-container {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .input-field {
        margin: 1 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
    ]

    def __init__(self):
        super().__init__()

    @staticmethod
    def extract_username_from_linkedin_url(input_str: str) -> str:
        """Extract username from LinkedIn URL or return the input if it's already a username.

        Args:
            input_str: Either a LinkedIn URL or a username

        Returns:
            The extracted username
        """
        input_str = input_str.strip()

        # Check if it looks like a URL
        if 'linkedin.com/in/' in input_str.lower():
            # Extract username from URL
            # Pattern matches: https://www.linkedin.com/in/username/ or similar variations
            match = re.search(r'linkedin\.com/in/([^/?]+)', input_str, re.IGNORECASE)
            if match:
                return match.group(1)

        # If not a URL or no match, return the input as-is (assume it's already a username)
        return input_str

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="add-profile-container"):
            yield Static("[bold cyan]Add New Profile[/bold cyan]\n", id="modal-title")
            yield Label("LinkedIn URL or Username (required):")
            yield Input(placeholder="e.g., https://linkedin.com/in/stephenvertex or stephenvertex", id="username-input", classes="input-field")
            yield Label("Name (required):")
            yield Input(placeholder="e.g., Stephen Douglas", id="name-input", classes="input-field")
            yield Label("Notes (optional):")
            yield Input(placeholder="Optional notes", id="notes-input", classes="input-field")
            with Horizontal(classes="button-row"):
                yield Button("Add", variant="success", id="add-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self):
        """Focus the username input when modal opens."""
        self.query_one("#username-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "add-button":
            username_input = self.query_one("#username-input", Input)
            name_input = self.query_one("#name-input", Input)
            notes_input = self.query_one("#notes-input", Input)

            username_or_url = username_input.value.strip()
            name = name_input.value.strip()
            notes = notes_input.value.strip()

            if not username_or_url or not name:
                # Show error (could add error message widget)
                return

            # Extract username from URL if provided
            username = self.extract_username_from_linkedin_url(username_or_url)

            self.dismiss({"username": username, "name": name, "notes": notes})
        else:
            self.dismiss(None)

    def action_dismiss(self):
        """Cancel the modal."""
        self.dismiss(None)


class EditProfileModal(Screen):
    """Modal screen for editing a profile."""

    CSS = """
    EditProfileModal {
        align: center middle;
    }

    #edit-profile-container {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .input-field {
        margin: 1 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
    ]

    def __init__(self, profile: Dict[str, Any]):
        super().__init__()
        self.profile = profile

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="edit-profile-container"):
            yield Static(f"[bold cyan]Edit Profile: {self.profile['username']}[/bold cyan]\n", id="modal-title")
            yield Label("Name:")
            yield Input(value=self.profile['name'], id="name-input", classes="input-field")
            yield Label("Notes:")
            yield Input(value=self.profile.get('notes', ''), id="notes-input", classes="input-field")
            yield Label("Active:")
            yield Static(f"[{'green' if self.profile['is_active'] else 'red'}]{'Yes' if self.profile['is_active'] else 'No'}[/] (press 'a' to toggle)")
            with Horizontal(classes="button-row"):
                yield Button("Save", variant="success", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self):
        """Focus the name input when modal opens."""
        self.query_one("#name-input", Input).focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        if event.key == "a":
            # Toggle active status
            self.profile['is_active'] = 0 if self.profile['is_active'] else 1
            # Update display
            active_display = self.query_one(Static)
            active_display.update(
                f"Active: [{'green' if self.profile['is_active'] else 'red'}]{'Yes' if self.profile['is_active'] else 'No'}[/] (press 'a' to toggle)"
            )
            event.prevent_default()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-button":
            name_input = self.query_one("#name-input", Input)
            notes_input = self.query_one("#notes-input", Input)

            name = name_input.value.strip()
            notes = notes_input.value.strip()

            if not name:
                return

            self.dismiss({
                "name": name,
                "notes": notes,
                "is_active": self.profile['is_active']
            })
        else:
            self.dismiss(None)

    def action_dismiss(self):
        """Cancel the modal."""
        self.dismiss(None)


class TagProfileModal(Screen):
    """Modal screen for tagging a profile."""

    CSS = """
    TagProfileModal {
        align: center middle;
    }

    #tag-profile-container {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .tag-item {
        padding: 0 1;
        margin: 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
        Binding("n", "new_tag", "New Tag"),
    ]

    def __init__(self, profile: Dict[str, Any], tag_manager: TagManager):
        super().__init__()
        self.profile = profile
        self.tag_manager = tag_manager
        self.all_tags = tag_manager.get_all_tags()
        self.profile_tag_ids = {tag['tag_id'] for tag in tag_manager.get_profile_tags(profile['profile_id'])}
        self.selected_tag_ids = self.profile_tag_ids.copy()

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="tag-profile-container"):
            yield Static(f"[bold cyan]Tag Profile: {self.profile['name']}[/bold cyan]\n", id="modal-title")
            yield Static(self._format_tags(), id="tag-list")
            yield Static("\n[dim]Press number to toggle tag, 'n' for new tag, ESC to cancel[/dim]", id="modal-help")
            with Horizontal(classes="button-row"):
                yield Button("Save", variant="success", id="save-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def _format_tags(self) -> str:
        """Format the tag list with current selections."""
        if not self.all_tags:
            return "[yellow]No tags available. Press 'n' to create a new tag.[/yellow]"

        lines = []
        for idx, tag in enumerate(self.all_tags, 1):
            is_selected = tag['tag_id'] in self.selected_tag_ids
            checkbox = "[✓]" if is_selected else "[ ]"
            style = f"bold {tag['color']}" if is_selected else tag['color']
            lines.append(f"[{style}]{checkbox} ({idx}) - {tag['name']}[/{style}]")
        return "\n".join(lines)

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for tag toggling."""
        # Check if it's a number key
        if event.key.isdigit():
            idx = int(event.key) - 1
            if 0 <= idx < len(self.all_tags):
                tag = self.all_tags[idx]
                if tag['tag_id'] in self.selected_tag_ids:
                    self.selected_tag_ids.remove(tag['tag_id'])
                else:
                    self.selected_tag_ids.add(tag['tag_id'])

                # Update display
                tag_list = self.query_one("#tag-list", Static)
                tag_list.update(self._format_tags())
                event.prevent_default()
                event.stop()

    def action_new_tag(self):
        """Open modal to create a new tag."""
        def handle_new_tag(result):
            if result:
                # Refresh tag list
                self.all_tags = self.tag_manager.get_all_tags()
                # Update display
                tag_list = self.query_one("#tag-list", Static)
                tag_list.update(self._format_tags())

        self.app.push_screen(CreateTagModal(self.tag_manager), handle_new_tag)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-button":
            self.dismiss(list(self.selected_tag_ids))
        else:
            self.dismiss(None)

    def action_dismiss(self):
        """Cancel the modal."""
        self.dismiss(None)


class CreateTagModal(Screen):
    """Modal screen for creating a new tag."""

    CSS = """
    CreateTagModal {
        align: center middle;
    }

    #create-tag-container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .input-field {
        margin: 1 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
    ]

    COLORS = ["cyan", "magenta", "green", "yellow", "blue", "red", "white"]

    def __init__(self, tag_manager: TagManager):
        super().__init__()
        self.tag_manager = tag_manager
        self.selected_color_idx = 0

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="create-tag-container"):
            yield Static("[bold cyan]Create New Tag[/bold cyan]\n", id="modal-title")
            yield Label("Tag Name:")
            yield Input(placeholder="e.g., aws, ai, startup", id="tag-name-input", classes="input-field")
            yield Label("Color (press 'c' to cycle):")
            yield Static(self._format_color_display(), id="color-display")
            with Horizontal(classes="button-row"):
                yield Button("Create", variant="success", id="create-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_mount(self):
        """Focus the tag name input when modal opens."""
        self.query_one("#tag-name-input", Input).focus()

    def _format_color_display(self) -> str:
        """Format the color display."""
        color = self.COLORS[self.selected_color_idx]
        return f"[{color}]● {color}[/{color}]"

    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        if event.key == "c":
            # Cycle through colors
            self.selected_color_idx = (self.selected_color_idx + 1) % len(self.COLORS)
            color_display = self.query_one("#color-display", Static)
            color_display.update(self._format_color_display())
            event.prevent_default()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "create-button":
            tag_name_input = self.query_one("#tag-name-input", Input)
            tag_name = tag_name_input.value.strip().lower()

            if not tag_name:
                return

            try:
                color = self.COLORS[self.selected_color_idx]
                tag_id = self.tag_manager.add_tag(tag_name, color)
                self.dismiss({"tag_id": tag_id, "name": tag_name, "color": color})
            except Exception as e:
                # Tag already exists or other error
                # Could show error message
                return
        else:
            self.dismiss(None)

    def action_dismiss(self):
        """Cancel the modal."""
        self.dismiss(None)


class ManageTagsModal(Screen):
    """Modal screen for managing global tags."""

    CSS = """
    ManageTagsModal {
        align: center middle;
    }

    #manage-tags-container {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .tag-item {
        padding: 0 1;
        margin: 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("n", "new_tag", "New Tag"),
        Binding("d", "delete_tag", "Delete Tag"),
    ]

    def __init__(self, tag_manager: TagManager):
        super().__init__()
        self.tag_manager = tag_manager
        self.tags_with_counts = []
        self.selected_idx = 0

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="manage-tags-container"):
            yield Static("[bold cyan]Manage Tags[/bold cyan]\n", id="modal-title")
            yield Static(self._format_tags(), id="tag-list")
            yield Static("\n[dim]Use number keys to select, 'd' to delete, 'n' for new tag[/dim]", id="modal-help")
            with Horizontal(classes="button-row"):
                yield Button("Close", variant="default", id="close-button")

    def on_mount(self):
        """Load tags when modal opens."""
        self.tags_with_counts = self.tag_manager.get_tags_with_counts()
        self._update_display()

    def _format_tags(self) -> str:
        """Format the tag list with usage counts."""
        if not self.tags_with_counts:
            return "[yellow]No tags available. Press 'n' to create a new tag.[/yellow]"

        lines = []
        for idx, tag in enumerate(self.tags_with_counts, 1):
            style = tag['color']
            selected = " [reverse]<--[/reverse]" if idx - 1 == self.selected_idx else ""
            lines.append(
                f"[{style}]({idx}) {tag['name']}[/{style}] - Used by {tag['usage_count']} profile(s){selected}"
            )
        return "\n".join(lines)

    def _update_display(self):
        """Update the tag list display."""
        tag_list = self.query_one("#tag-list", Static)
        tag_list.update(self._format_tags())

    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        if event.key.isdigit():
            idx = int(event.key) - 1
            if 0 <= idx < len(self.tags_with_counts):
                self.selected_idx = idx
                self._update_display()
                event.prevent_default()
                event.stop()

    def action_new_tag(self):
        """Create a new tag."""
        def handle_new_tag(result):
            if result:
                self.tags_with_counts = self.tag_manager.get_tags_with_counts()
                self._update_display()

        self.app.push_screen(CreateTagModal(self.tag_manager), handle_new_tag)

    def action_delete_tag(self):
        """Delete the selected tag."""
        if not self.tags_with_counts:
            return

        if 0 <= self.selected_idx < len(self.tags_with_counts):
            tag = self.tags_with_counts[self.selected_idx]

            # Show confirmation if tag is in use
            if tag['usage_count'] > 0:
                # Could add confirmation modal
                # For now, just delete
                pass

            self.tag_manager.delete_tag(tag['tag_id'])
            self.tags_with_counts = self.tag_manager.get_tags_with_counts()
            if self.selected_idx >= len(self.tags_with_counts):
                self.selected_idx = max(0, len(self.tags_with_counts) - 1)
            self._update_display()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        self.dismiss(None)

    def action_dismiss(self):
        """Close the modal."""
        self.dismiss(None)


class FilterByTagModal(Screen):
    """Modal screen for filtering profiles by tags."""

    CSS = """
    FilterByTagModal {
        align: center middle;
    }

    #filter-tag-container {
        width: 70;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    .tag-item {
        padding: 0 1;
        margin: 0;
    }

    .button-row {
        align: center middle;
        padding: 1 0;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
        Binding("m", "toggle_match_mode", "Toggle AND/OR"),
    ]

    def __init__(self, tag_manager: TagManager, current_filters: List[str] = None):
        super().__init__()
        self.tag_manager = tag_manager
        self.all_tags = tag_manager.get_all_tags()
        self.selected_tag_names = set(current_filters or [])
        self.match_all = False  # False = OR, True = AND

    def compose(self) -> ComposeResult:
        """Create the modal content."""
        with Container(id="filter-tag-container"):
            yield Static("[bold cyan]Filter Profiles by Tags[/bold cyan]\n", id="modal-title")
            yield Static(self._format_match_mode(), id="match-mode")
            yield Static(self._format_tags(), id="tag-list")
            yield Static("\n[dim]Press number to toggle tag, 'm' for AND/OR, ESC to cancel[/dim]", id="modal-help")
            with Horizontal(classes="button-row"):
                yield Button("Apply", variant="success", id="apply-button")
                yield Button("Clear", variant="default", id="clear-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def _format_match_mode(self) -> str:
        """Format the match mode display."""
        mode = "ALL tags (AND)" if self.match_all else "ANY tag (OR)"
        return f"[bold]Match Mode:[/bold] [{mode}]"

    def _format_tags(self) -> str:
        """Format the tag list with current selections."""
        if not self.all_tags:
            return "[yellow]No tags available.[/yellow]"

        lines = []
        for idx, tag in enumerate(self.all_tags, 1):
            is_selected = tag['name'] in self.selected_tag_names
            checkbox = "[✓]" if is_selected else "[ ]"
            style = f"bold {tag['color']}" if is_selected else tag['color']
            lines.append(f"[{style}]{checkbox} ({idx}) - {tag['name']}[/{style}]")
        return "\n".join(lines)

    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        if event.key.isdigit():
            idx = int(event.key) - 1
            if 0 <= idx < len(self.all_tags):
                tag = self.all_tags[idx]
                if tag['name'] in self.selected_tag_names:
                    self.selected_tag_names.remove(tag['name'])
                else:
                    self.selected_tag_names.add(tag['name'])

                # Update display
                tag_list = self.query_one("#tag-list", Static)
                tag_list.update(self._format_tags())
                event.prevent_default()
                event.stop()

    def action_toggle_match_mode(self):
        """Toggle between AND and OR match modes."""
        self.match_all = not self.match_all
        match_mode_display = self.query_one("#match-mode", Static)
        match_mode_display.update(self._format_match_mode())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "apply-button":
            self.dismiss({
                "tag_names": list(self.selected_tag_names),
                "match_all": self.match_all
            })
        elif event.button.id == "clear-button":
            self.dismiss({"tag_names": [], "match_all": False})
        else:
            self.dismiss(None)

    def action_dismiss(self):
        """Cancel the modal."""
        self.dismiss(None)


class ProfileManagementScreen(Screen):
    """Main screen for managing profiles."""

    CSS = """
    ProfileManagementScreen DataTable {
        height: 1fr;
    }

    #profile-status-bar {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "back_to_main", "Back to Posts", priority=True),
        Binding("a", "add_profile", "Add Profile"),
        Binding("d", "delete_profile", "Delete Profile"),
        Binding("e", "edit_profile", "Edit Profile"),
        Binding("t", "tag_profile", "Tag Profile"),
        Binding("T", "manage_tags", "Manage Tags", key_display="shift+t"),
        Binding("f", "filter_by_tag", "Filter by Tag"),
        Binding("c", "clear_filter", "Clear Filter"),
        Binding("s", "sync_csv", "Sync CSV"),
        Binding("o", "open_profile_url", "Open LinkedIn"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self, db_path: str = "data/posts.db"):
        super().__init__()
        self.db_path = db_path  # Kept for backwards compatibility, but not used
        self.profile_manager = ProfileManager()
        self.tag_manager = TagManager()
        self.profiles = []
        self.profile_index_map = {}  # Maps row key to profile index
        self.current_filter_tags = []
        self.current_filter_match_all = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the screen."""
        yield Header()
        yield Static(id="profile-status-bar")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """Set up the table when the screen starts."""
        table = self.query_one(DataTable)
        table.add_column("ID", key="id", width=6)
        table.add_column("Username", key="username", width=20)
        table.add_column("Name", key="name", width=25)
        table.add_column("Tags", key="tags", width=30)
        table.add_column("Active", key="active", width=8)
        table.add_column("Posts", key="posts", width=8)

        self.load_and_display_profiles()
        table.focus()

    def load_and_display_profiles(self, preserve_cursor_profile_id: Optional[int] = None):
        """Load profiles and populate the table.

        Args:
            preserve_cursor_profile_id: If provided, restore cursor to this profile ID after reload
        """
        if self.current_filter_tags:
            self.profiles = self.profile_manager.get_profiles_by_tags(
                self.current_filter_tags,
                match_all=self.current_filter_match_all
            )
        else:
            self.profiles = self.profile_manager.get_all_profiles()

        # Populate table
        table = self.query_one(DataTable)
        table.clear()
        self.profile_index_map.clear()

        target_row_idx = None
        for idx, profile in enumerate(self.profiles):
            tags = self.tag_manager.get_profile_tag_names(profile['profile_id'])
            tag_display = ', '.join(f"[{self._get_tag_color(tag)}]{tag}[/]" for tag in tags)

            active_display = "[green]Yes[/]" if profile['is_active'] else "[red]No[/]"

            row_key = table.add_row(
                str(profile['profile_id']),
                profile['username'],
                profile['name'],
                tag_display,
                active_display,
                str(profile.get('post_count', 0))
            )
            self.profile_index_map[row_key] = idx

            # Track the row index if this is the profile we want to restore cursor to
            if preserve_cursor_profile_id and profile['profile_id'] == preserve_cursor_profile_id:
                target_row_idx = idx

        self.update_status_bar()

        # Restore cursor position if requested
        if target_row_idx is not None:
            table.move_cursor(row=target_row_idx)

    def _get_tag_color(self, tag_name: str) -> str:
        """Get the color for a tag name."""
        tag = self.tag_manager.get_tag_by_name(tag_name)
        return tag['color'] if tag else 'white'

    def update_status_bar(self):
        """Update the status bar with profile counts."""
        status_bar = self.query_one("#profile-status-bar", Static)
        filter_status = ""
        if self.current_filter_tags:
            mode = "ALL" if self.current_filter_match_all else "ANY"
            tags_str = ', '.join(self.current_filter_tags)
            filter_status = f" (Filter: {mode} of [{tags_str}])"

        total = self.profile_manager.get_profile_count()
        status_bar.update(f"Showing {len(self.profiles)} of {total} profiles{filter_status}")

    def action_add_profile(self):
        """Open modal to add a new profile."""
        def handle_add(result):
            if result:
                try:
                    self.profile_manager.add_profile(
                        result['username'],
                        result['name'],
                        result['notes']
                    )
                    self.load_and_display_profiles()
                except Exception as e:
                    # Username already exists or other error
                    pass

        self.app.push_screen(AddProfileModal(), handle_add)

    def action_delete_profile(self):
        """Delete the currently selected profile."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.profile_index_map:
                    profile_idx = self.profile_index_map[row_key]
                    profile = self.profiles[profile_idx]

                    # Delete profile
                    self.profile_manager.delete_profile(profile['profile_id'])
                    self.load_and_display_profiles()

    def action_edit_profile(self):
        """Edit the currently selected profile."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.profile_index_map:
                    profile_idx = self.profile_index_map[row_key]
                    profile = self.profiles[profile_idx]

                    def handle_edit(result):
                        if result:
                            self.profile_manager.update_profile(
                                profile['profile_id'],
                                **result
                            )
                            # Preserve cursor on the profile we just edited
                            self.load_and_display_profiles(preserve_cursor_profile_id=profile['profile_id'])

                    self.app.push_screen(EditProfileModal(profile), handle_edit)

    def action_tag_profile(self):
        """Tag the currently selected profile."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.profile_index_map:
                    profile_idx = self.profile_index_map[row_key]
                    profile = self.profiles[profile_idx]

                    def handle_tag(result):
                        if result is not None:
                            self.tag_manager.set_profile_tags(profile['profile_id'], result)
                            # Preserve cursor on the profile we just tagged
                            self.load_and_display_profiles(preserve_cursor_profile_id=profile['profile_id'])

                    self.app.push_screen(
                        TagProfileModal(profile, self.tag_manager),
                        handle_tag
                    )

    def action_manage_tags(self):
        """Open modal to manage global tags."""
        self.app.push_screen(ManageTagsModal(self.tag_manager))

    def action_filter_by_tag(self):
        """Filter profiles by tags."""
        def handle_filter(result):
            if result is not None:
                self.current_filter_tags = result['tag_names']
                self.current_filter_match_all = result['match_all']
                self.load_and_display_profiles()

        self.app.push_screen(
            FilterByTagModal(self.tag_manager, self.current_filter_tags),
            handle_filter
        )

    def action_clear_filter(self):
        """Clear tag filters."""
        self.current_filter_tags = []
        self.current_filter_match_all = False
        self.load_and_display_profiles()

    def action_sync_csv(self):
        """Sync profiles with CSV file."""
        stats = self.profile_manager.sync_from_csv()
        self.profile_manager.export_to_csv()
        self.load_and_display_profiles()

        # Could show notification with stats
        # For now, just refresh

    def action_open_profile_url(self):
        """Open the LinkedIn profile URL of the currently selected profile."""
        table = self.query_one(DataTable)
        cursor_row = table.cursor_row

        if cursor_row is not None:
            row_keys = list(table.rows.keys())
            if cursor_row < len(row_keys):
                row_key = row_keys[cursor_row]

                if row_key in self.profile_index_map:
                    profile_idx = self.profile_index_map[row_key]
                    profile = self.profiles[profile_idx]
                    username = profile['username']
                    url = f"https://linkedin.com/in/{username}"
                    subprocess.run(["open", url])

    def action_back_to_main(self):
        """Return to the main posts screen."""
        self.dismiss()

    def action_cursor_down(self):
        """Move cursor down."""
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self):
        """Move cursor up."""
        table = self.query_one(DataTable)
        table.action_cursor_up()
