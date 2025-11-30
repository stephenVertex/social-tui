"""Profile management for social-tui with AWS-style identifiers."""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from db_utils import generate_aws_id, PREFIX_PROFILE


class ProfileManager:
    """Manages profile data in SQLite database with AWS-style IDs."""

    def __init__(self, db_path: str = "data/posts_v2.db"):
        """Initialize ProfileManager with database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory and foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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
            sqlite3.IntegrityError: If username already exists
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            profile_id = generate_aws_id(PREFIX_PROFILE)

            cursor.execute("""
                INSERT INTO profiles (
                    profile_id, username, name, platform, notes,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                profile_id, username, name, platform, notes,
                datetime.now().isoformat(),
                datetime.now().isoformat()
            ))

            conn.commit()
            return profile_id
        finally:
            conn.close()

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile from the database.

        Args:
            profile_id: ID of the profile to delete

        Returns:
            True if profile was deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM profiles WHERE profile_id = ?", (profile_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

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
        kwargs['updated_at'] = datetime.now().isoformat()

        # Build UPDATE query
        fields = ', '.join(f"{key} = ?" for key in kwargs.keys())
        values = list(kwargs.values())
        values.append(profile_id)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(f"UPDATE profiles SET {fields} WHERE profile_id = ?", values)
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        finally:
            conn.close()

    def get_profile_by_id(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get a profile by ID.

        Args:
            profile_id: ID of the profile

        Returns:
            Profile dictionary or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_profile_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a profile by username.

        Args:
            username: LinkedIn username

        Returns:
            Profile dictionary or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM profiles WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_profiles(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """Get all profiles from the database.

        Args:
            active_only: If True, only return active profiles

        Returns:
            List of profile dictionaries with post_count field
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if active_only:
                cursor.execute("""
                    SELECT p.*, COUNT(posts.post_id) as post_count
                    FROM profiles p
                    LEFT JOIN posts ON p.username = posts.author_username
                    WHERE p.is_active = 1
                    GROUP BY p.profile_id
                    ORDER BY p.name
                """)
            else:
                cursor.execute("""
                    SELECT p.*, COUNT(posts.post_id) as post_count
                    FROM profiles p
                    LEFT JOIN posts ON p.username = posts.author_username
                    GROUP BY p.profile_id
                    ORDER BY p.name
                """)

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_profiles_by_tag(self, tag_name: str) -> List[Dict[str, Any]]:
        """Get all profiles with a specific tag.

        Args:
            tag_name: Name of the tag to filter by

        Returns:
            List of profile dictionaries with post_count field
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT DISTINCT p.profile_id, p.username, p.name, p.platform,
                       p.notes, p.is_active, p.created_at, p.updated_at,
                       p.last_synced_at, COUNT(posts.post_id) as post_count
                FROM profiles p
                JOIN profile_tags pt ON p.profile_id = pt.profile_id
                JOIN tags t ON pt.tag_id = t.tag_id
                LEFT JOIN posts ON p.username = posts.author_username
                WHERE t.name = ?
                GROUP BY p.profile_id
                ORDER BY p.name
            """, (tag_name,))

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_profiles_by_tags(self, tag_names: List[str], match_all: bool = False) -> List[Dict[str, Any]]:
        """Get profiles matching tags.

        Args:
            tag_names: List of tag names to filter by
            match_all: If True, profile must have ALL tags (AND). If False, ANY tag (OR)

        Returns:
            List of profile dictionaries with post_count field
        """
        if not tag_names:
            return self.get_all_profiles()

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if match_all:
                # Profile must have ALL tags (AND)
                placeholders = ','.join('?' * len(tag_names))
                cursor.execute(f"""
                    SELECT p.*, COUNT(posts.post_id) as post_count
                    FROM profiles p
                    LEFT JOIN posts ON p.username = posts.author_username
                    WHERE (
                        SELECT COUNT(DISTINCT t.name)
                        FROM profile_tags pt
                        JOIN tags t ON pt.tag_id = t.tag_id
                        WHERE pt.profile_id = p.profile_id AND t.name IN ({placeholders})
                    ) = ?
                    GROUP BY p.profile_id
                    ORDER BY p.name
                """, tag_names + [len(tag_names)])
            else:
                # Profile must have ANY tag (OR)
                placeholders = ','.join('?' * len(tag_names))
                cursor.execute(f"""
                    SELECT DISTINCT p.profile_id, p.username, p.name, p.platform,
                           p.notes, p.is_active, p.created_at, p.updated_at,
                           p.last_synced_at, COUNT(posts.post_id) as post_count
                    FROM profiles p
                    JOIN profile_tags pt ON p.profile_id = pt.profile_id
                    JOIN tags t ON pt.tag_id = t.tag_id
                    LEFT JOIN posts ON p.username = posts.author_username
                    WHERE t.name IN ({placeholders})
                    GROUP BY p.profile_id
                    ORDER BY p.name
                """, tag_names)

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

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
                        last_synced_at=datetime.now().isoformat()
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
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM profiles")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def search_profiles(self, query: str) -> List[Dict[str, Any]]:
        """Search profiles by name or username.

        Args:
            query: Search query string

        Returns:
            List of matching profile dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT * FROM profiles
                WHERE name LIKE ? OR username LIKE ?
                ORDER BY name
            """, (search_pattern, search_pattern))

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
