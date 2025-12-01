"""Profile management for social-tui with AWS-style identifiers."""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Any

from supabase_client import get_supabase_client
from db_utils import generate_aws_id, PREFIX_PROFILE


class ProfileManager:
    """Manages profile data in Supabase database with AWS-style IDs."""

    def __init__(self):
        """Initialize ProfileManager with Supabase connection."""
        self.client = get_supabase_client()

    def add_profile(self, username: str, name: str, notes: str = "", platform: str = "linkedin") -> str:
        """Add a new profile to the database.

        Args:
            username: LinkedIn username (unique)
            name: Full name of the profile
            notes: Optional notes about the profile
            platform: Social platform (default: linkedin)

        Returns:
            Profile ID of the newly created profile (AWS-style)

        Raises:
            Exception: If username already exists
        """
        profile_id = generate_aws_id(PREFIX_PROFILE)

        self.client.table('profiles').insert({
            'profile_id': profile_id,
            'username': username,
            'name': name,
            'platform': platform,
            'notes': notes,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).execute()

        return profile_id

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile from the database.

        Args:
            profile_id: ID of the profile to delete

        Returns:
            True if profile was deleted, False if not found
        """
        result = self.client.table('profiles').delete().eq('profile_id', profile_id).execute()
        return len(result.data) > 0

    def update_profile(self, profile_id: str, **kwargs) -> bool:
        """Update profile fields.

        Args:
            profile_id: ID of the profile to update
            **kwargs: Fields to update (username, name, notes, is_active, platform, etc.)

        Returns:
            True if profile was updated, False if not found
        """
        if not kwargs:
            return False

        # Always update the updated_at timestamp
        kwargs['updated_at'] = datetime.now(timezone.utc).isoformat()

        result = self.client.table('profiles').update(kwargs).eq('profile_id', profile_id).execute()
        return len(result.data) > 0

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get a profile by ID.

        Args:
            profile_id: ID of the profile

        Returns:
            Profile dictionary or None if not found
        """
        result = self.client.table('profiles').select('*').eq('profile_id', profile_id).execute()
        return result.data[0] if result.data else None

    def get_profile_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a profile by username.

        Args:
            username: LinkedIn username

        Returns:
            Profile dictionary or None if not found
        """
        result = self.client.table('profiles').select('*').eq('username', username).execute()
        return result.data[0] if result.data else None

    def get_all_profiles(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Get all profiles from the database.

        Args:
            active_only: If True, only return active profiles

        Returns:
            List of profile dictionaries with post_count and tags fields
        """
        # Query from the optimized view (replaces 3N+2 queries with 1 query)
        query = self.client.table('v_profiles_with_stats').select('*')

        if active_only:
            query = query.eq('is_active', True)

        result = query.execute()
        return result.data

    def get_profiles_by_tag(self, tag_name: str) -> List[Dict[str, Any]]:
        """Get all profiles with a specific tag.

        Args:
            tag_name: Name of the tag to filter by

        Returns:
            List of profile dictionaries with post_count field
        """
        # First, get the tag by name
        tag_result = self.client.table('tags').select('tag_id').eq('name', tag_name).execute()
        if not tag_result.data:
            return []

        tag_id = tag_result.data[0]['tag_id']

        # Get profile_ids that have this tag
        pt_result = self.client.table('profile_tags').select('profile_id').eq('tag_id', tag_id).execute()
        if not pt_result.data:
            return []

        profile_ids = [pt['profile_id'] for pt in pt_result.data]

        # Get profiles
        profiles_result = self.client.table('profiles').select('*').in_('profile_id', profile_ids).order('created_at', desc=True).execute()
        profiles = profiles_result.data

        # Add post counts
        for profile in profiles:
            posts_result = self.client.table('posts').select('post_id', count='exact').eq('author_username', profile['username']).execute()
            profile['post_count'] = posts_result.count if posts_result.count is not None else 0

        return profiles

    def get_profiles_by_tags(self, tag_names: List[str], match_all: bool = False) -> List[Dict[str, Any]]:
        """Get profiles matching tags.

        Args:
            tag_names: List of tag names to filter by
            match_all: If True, profile must have ALL tags (AND). If False, ANY tag (OR)

        Returns:
            List of profile dictionaries with post_count and tags fields
        """
        if not tag_names:
            return self.get_all_profiles()

        # Get all profiles from the optimized view
        all_profiles = self.get_all_profiles()

        # Filter profiles based on tags (client-side filtering)
        # Normalize tag names for comparison
        search_tags = set(tag.lower() for tag in tag_names)

        matching_profiles = []
        for profile in all_profiles:
            # Extract tag names from the tags JSON array
            profile_tag_names = set()
            if profile.get('tags'):
                for tag in profile['tags']:
                    if isinstance(tag, dict) and 'name' in tag:
                        profile_tag_names.add(tag['name'].lower())

            # Check if profile matches the filter criteria
            if match_all:
                # Profile must have ALL tags
                if search_tags.issubset(profile_tag_names):
                    matching_profiles.append(profile)
            else:
                # Profile must have ANY tag
                if search_tags.intersection(profile_tag_names):
                    matching_profiles.append(profile)

        return matching_profiles

    def sync_from_csv(self, csv_path: str = "data/input-data.csv") -> Dict[str, int]:
        """Import profiles from CSV file. Updates existing profiles by username.

        Args:
            csv_path: Path to CSV file with columns: name, username

        Returns:
            Dictionary with counts: {"added": 0, "updated": 0, "skipped": 0}
        """
        stats = {"added": 0, "updated": 0, "skipped": 0}

        csv_file = Path(csv_path)
        if not csv_file.exists():
            return stats

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Skip empty rows
                if not row.get('username') or not row.get('name'):
                    stats["skipped"] += 1
                    continue

                username = row['username'].strip()
                name = row['name'].strip()

                # Check if profile exists
                existing = self.get_profile_by_username(username)

                if existing:
                    # Update existing profile
                    self.update_profile(
                        existing['profile_id'],
                        name=name,
                        last_synced_at=datetime.now(timezone.utc).isoformat()
                    )
                    stats["updated"] += 1
                else:
                    # Add new profile
                    self.add_profile(username, name)
                    stats["added"] += 1

        return stats

    def export_to_csv(self, csv_path: str = "data/input-data.csv", active_only: bool = True):
        """Export profiles to CSV file.

        Args:
            csv_path: Path to CSV file
            active_only: If True, only export active profiles
        """
        profiles = self.get_all_profiles(active_only=active_only)

        # Ensure directory exists
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)

        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'username'])
            writer.writeheader()

            for profile in profiles:
                writer.writerow({
                    'name': profile['name'],
                    'username': profile['username']
                })

    def get_profile_count(self) -> int:
        """Get total number of profiles.

        Returns:
            Total profile count
        """
        result = self.client.table('profiles').select('profile_id', count='exact').execute()
        return result.count if result.count is not None else 0

    def search_profiles(self, query: str) -> List[Dict[str, Any]]:
        """Search profiles by name or username.

        Args:
            query: Search query string

        Returns:
            List of matching profile dictionaries
        """
        # Supabase uses ilike for case-insensitive LIKE queries
        search_pattern = f"%{query}%"

        # Search in name
        name_results = self.client.table('profiles').select('*').ilike('name', search_pattern).execute()

        # Search in username
        username_results = self.client.table('profiles').select('*').ilike('username', search_pattern).execute()

        # Combine and deduplicate by profile_id
        profiles_dict = {}
        for profile in name_results.data + username_results.data:
            profiles_dict[profile['profile_id']] = profile

        # Sort by name
        profiles = sorted(profiles_dict.values(), key=lambda p: p['name'])
        return profiles
