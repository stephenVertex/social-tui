"""Tag management for social-tui profiles with AWS-style identifiers."""

from datetime import datetime
from typing import List, Dict, Optional, Any

from supabase_client import get_supabase_client
from db_utils import generate_aws_id, PREFIX_TAG, PREFIX_PROFILE_TAG


class TagManager:
    """Manages tags and profile-tag relationships with AWS-style IDs."""

    # Default tag colors
    DEFAULT_COLORS = {
        "aws": "cyan",
        "ai": "magenta",
        "startup": "green",
        "finops": "yellow",
        "cloud": "blue",
        "ml": "red",
    }

    def __init__(self):
        """Initialize TagManager with Supabase connection."""
        self.client = get_supabase_client()
        self._ensure_default_tags()

    def _ensure_default_tags(self):
        """Create default tags if they don't exist."""
        default_tags = ["aws", "ai", "startup"]

        for tag_name in default_tags:
            # Check if tag exists
            existing = self.get_tag_by_name(tag_name)
            if not existing:
                color = self.DEFAULT_COLORS.get(tag_name, "white")
                self.add_tag(tag_name, color)

    def add_tag(self, name: str, color: str = "cyan", description: str = None) -> str:
        """Add a new tag to the database.

        Args:
            name: Tag name (must be unique)
            color: Color for the tag (default: cyan)
            description: Optional description of the tag

        Returns:
            Tag ID of the newly created tag (AWS-style)

        Raises:
            Exception: If tag name already exists
        """
        # Normalize tag name to lowercase
        name = name.lower().strip()
        tag_id = generate_aws_id(PREFIX_TAG)

        self.client.table('tags').insert({
            'tag_id': tag_id,
            'name': name,
            'description': description,
            'color': color,
            'created_at': datetime.now().isoformat()
        }).execute()

        return tag_id

    def delete_tag(self, tag_id: str) -> bool:
        """Delete a tag from the database.

        This will also remove all profile-tag associations (CASCADE).

        Args:
            tag_id: ID of the tag to delete

        Returns:
            True if tag was deleted, False if not found
        """
        result = self.client.table('tags').delete().eq('tag_id', tag_id).execute()
        return len(result.data) > 0

    def rename_tag(self, tag_id: str, new_name: str) -> bool:
        """Rename a tag.

        Args:
            tag_id: ID of the tag to rename
            new_name: New name for the tag

        Returns:
            True if tag was renamed, False if not found

        Raises:
            Exception: If new name already exists
        """
        # Normalize tag name to lowercase
        new_name = new_name.lower().strip()

        result = self.client.table('tags').update({
            'name': new_name
        }).eq('tag_id', tag_id).execute()

        return len(result.data) > 0

    def update_tag_color(self, tag_id: str, color: str) -> bool:
        """Update tag color.

        Args:
            tag_id: ID of the tag
            color: New color for the tag

        Returns:
            True if tag was updated, False if not found
        """
        result = self.client.table('tags').update({
            'color': color
        }).eq('tag_id', tag_id).execute()

        return len(result.data) > 0

    def update_tag_description(self, tag_id: str, description: str) -> bool:
        """Update tag description.

        Args:
            tag_id: ID of the tag
            description: New description for the tag

        Returns:
            True if tag was updated, False if not found
        """
        result = self.client.table('tags').update({
            'description': description
        }).eq('tag_id', tag_id).execute()

        return len(result.data) > 0

    def get_tag_by_id(self, tag_id: str) -> Optional[Dict[str, Any]]:
        """Get a tag by ID.

        Args:
            tag_id: ID of the tag

        Returns:
            Tag dictionary or None if not found
        """
        result = self.client.table('tags').select('*').eq('tag_id', tag_id).execute()
        return result.data[0] if result.data else None

    def get_tag_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a tag by name.

        Args:
            name: Name of the tag

        Returns:
            Tag dictionary or None if not found
        """
        # Normalize tag name to lowercase
        name = name.lower().strip()

        result = self.client.table('tags').select('*').eq('name', name).execute()
        return result.data[0] if result.data else None

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Get all tags from the database.

        Returns:
            List of tag dictionaries, sorted by name
        """
        result = self.client.table('tags').select('*').order('name').execute()
        return result.data

    def get_tags_with_counts(self) -> List[Dict[str, Any]]:
        """Get all tags with usage counts.

        Returns:
            List of tag dictionaries with 'usage_count' field
        """
        # Get all tags
        tags_result = self.client.table('tags').select('*').order('name').execute()
        tags = tags_result.data

        # Get counts for each tag
        for tag in tags:
            count_result = self.client.table('profile_tags').select('profile_tag_id', count='exact').eq('tag_id', tag['tag_id']).execute()
            tag['usage_count'] = count_result.count if count_result.count is not None else 0

        return tags

    def tag_profile(self, profile_id: str, tag_id: str) -> bool:
        """Add a tag to a profile.

        Args:
            profile_id: ID of the profile
            tag_id: ID of the tag

        Returns:
            True if tag was added, False if already tagged or error

        Raises:
            Exception: If the profile-tag combination already exists
        """
        try:
            profile_tag_id = generate_aws_id(PREFIX_PROFILE_TAG)

            self.client.table('profile_tags').insert({
                'profile_tag_id': profile_tag_id,
                'profile_id': profile_id,
                'tag_id': tag_id,
                'created_at': datetime.now().isoformat()
            }).execute()

            return True
        except Exception as e:
            # Check if it's a duplicate constraint error
            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                return False
            raise

    def untag_profile(self, profile_id: str, tag_id: str) -> bool:
        """Remove a tag from a profile.

        Args:
            profile_id: ID of the profile
            tag_id: ID of the tag

        Returns:
            True if tag was removed, False if not found
        """
        result = self.client.table('profile_tags').delete().eq('profile_id', profile_id).eq('tag_id', tag_id).execute()
        return len(result.data) > 0

    def get_profile_tags(self, profile_id: str) -> List[Dict[str, Any]]:
        """Get all tags for a specific profile.

        Args:
            profile_id: ID of the profile

        Returns:
            List of tag dictionaries
        """
        # Get profile_tag associations for this profile
        pt_result = self.client.table('profile_tags').select('tag_id').eq('profile_id', profile_id).execute()

        if not pt_result.data:
            return []

        # Get tag IDs
        tag_ids = [pt['tag_id'] for pt in pt_result.data]

        # Get the actual tags
        tags_result = self.client.table('tags').select('*').in_('tag_id', tag_ids).order('name').execute()
        return tags_result.data

    def get_profile_tag_names(self, profile_id: str) -> List[str]:
        """Get tag names for a profile.

        Args:
            profile_id: ID of the profile

        Returns:
            List of tag names
        """
        tags = self.get_profile_tags(profile_id)
        return [tag['name'] for tag in tags]

    def set_profile_tags(self, profile_id: str, tag_ids: List[str]):
        """Set tags for a profile (replaces existing tags).

        Args:
            profile_id: ID of the profile
            tag_ids: List of tag IDs to assign
        """
        # Remove all existing tags
        self.client.table('profile_tags').delete().eq('profile_id', profile_id).execute()

        # Add new tags
        if tag_ids:
            new_tags = []
            for tag_id in tag_ids:
                profile_tag_id = generate_aws_id(PREFIX_PROFILE_TAG)
                new_tags.append({
                    'profile_tag_id': profile_tag_id,
                    'profile_id': profile_id,
                    'tag_id': tag_id,
                    'created_at': datetime.now().isoformat()
                })

            self.client.table('profile_tags').insert(new_tags).execute()

    def get_or_create_tag(self, name: str, color: str = "cyan", description: str = None) -> Dict[str, Any]:
        """Get a tag by name, or create it if it doesn't exist.

        Args:
            name: Tag name
            color: Color for the tag if creating new (default: cyan)
            description: Optional description if creating new

        Returns:
            Tag dictionary
        """
        # Try to get existing tag
        tag = self.get_tag_by_name(name)

        if not tag:
            # Create new tag
            tag_id = self.add_tag(name, color, description)
            tag = self.get_tag_by_id(tag_id)

        return tag

    def clear_profile_tags(self, profile_id: str):
        """Remove all tags from a profile.

        Args:
            profile_id: ID of the profile
        """
        self.client.table('profile_tags').delete().eq('profile_id', profile_id).execute()

    def get_profiles_by_tag(self, tag_id: str) -> List[str]:
        """Get all profile IDs that have a specific tag.

        Args:
            tag_id: ID of the tag

        Returns:
            List of profile IDs
        """
        result = self.client.table('profile_tags').select('profile_id').eq('tag_id', tag_id).order('created_at').execute()
        return [row['profile_id'] for row in result.data]
