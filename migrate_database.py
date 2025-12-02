#!/usr/bin/env python3
"""
Database migration script for social-tui.
Migrates from the old schema to the new schema with AWS-style identifiers.

Usage:
    python migrate_database.py --source data/posts.db --output data/posts_v2.db
    python migrate_database.py --source data/posts.db --output data/posts_v2.db --dry-run
"""

import sqlite3
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import sys

from db_utils import (
    generate_aws_id,
    PREFIX_POST,
    PREFIX_DOWNLOAD,
    PREFIX_RUN,
    PREFIX_PROFILE,
    PREFIX_TAG,
    PREFIX_PROFILE_TAG,
    PREFIX_POST_TAG,
    PREFIX_ACTION,
    PREFIX_MEDIA,
)


class DatabaseMigration:
    """Handles migration from old schema to new schema."""

    def __init__(self, source_db: str, output_db: str, dry_run: bool = False):
        """Initialize migration.

        Args:
            source_db: Path to source database
            output_db: Path to output database
            dry_run: If True, don't write to output database
        """
        self.source_db = source_db
        self.output_db = output_db
        self.dry_run = dry_run
        self.stats = {
            "posts": {"total": 0, "migrated": 0, "errors": 0},
            "profiles": {"total": 0, "migrated": 0, "errors": 0},
            "tags": {"total": 0, "migrated": 0, "errors": 0},
            "profile_tags": {"total": 0, "migrated": 0, "errors": 0},
        }
        # ID mapping for foreign key updates
        self.id_mapping = {
            "profiles": {},  # old_id -> new_id
            "tags": {},  # old_id -> new_id
        }

    def create_new_schema(self, conn: sqlite3.Connection):
        """Create the new database schema."""
        cursor = conn.cursor()

        print("Creating new schema...")

        # Posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT PRIMARY KEY,
                urn TEXT UNIQUE NOT NULL,
                full_urn TEXT,
                platform TEXT DEFAULT 'linkedin',
                posted_at_timestamp INTEGER NOT NULL,
                author_username TEXT,
                text_content TEXT,
                post_type TEXT,
                url TEXT,
                raw_json TEXT,
                first_seen_at TIMESTAMP,
                is_read BOOLEAN DEFAULT 0,
                is_marked BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for posts
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_urn ON posts(urn)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_posted_at ON posts(posted_at_timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_first_seen ON posts(first_seen_at)")

        # DataDownloads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_downloads (
                download_id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                run_id TEXT,
                downloaded_at TIMESTAMP NOT NULL,
                total_reactions INTEGER DEFAULT 0,
                stats_json TEXT,
                raw_json TEXT,
                source_file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
                FOREIGN KEY (run_id) REFERENCES download_runs(run_id) ON DELETE SET NULL
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_downloads_post_id ON data_downloads(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_downloads_run_id ON data_downloads(run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_downloads_downloaded_at ON data_downloads(downloaded_at)")

        # DownloadRuns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_runs (
                run_id TEXT PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',
                script_name TEXT,
                platform TEXT DEFAULT 'linkedin',
                posts_fetched INTEGER DEFAULT 0,
                posts_new INTEGER DEFAULT 0,
                posts_updated INTEGER DEFAULT 0,
                error_message TEXT,
                system_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_started_at ON download_runs(started_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON download_runs(status)")

        # Profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                platform TEXT DEFAULT 'linkedin',
                is_active BOOLEAN DEFAULT 1,
                notes TEXT,
                post_count INTEGER DEFAULT 0,
                last_synced_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_username ON profiles(username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_active ON profiles(is_active)")

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                tag_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                color TEXT DEFAULT 'cyan',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")

        # ProfileTags junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_tags (
                profile_tag_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                tag_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                UNIQUE(profile_id, tag_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_tags_profile ON profile_tags(profile_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_tags_tag ON profile_tags(tag_id)")

        # PostTags junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_tags (
                post_tag_id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                tag_id TEXT NOT NULL,
                confidence REAL,
                applied_by TEXT DEFAULT 'ai',
                system_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                UNIQUE(post_id, tag_id)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_post_tags_post ON post_tags(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_post_tags_tag ON post_tags(tag_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_post_tags_applied_by ON post_tags(applied_by)")

        # ActionQueue table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_queue (
                action_id TEXT PRIMARY KEY,
                post_id TEXT,
                action_type TEXT NOT NULL,
                action_params TEXT,
                status TEXT DEFAULT 'queued',
                priority INTEGER DEFAULT 0,
                scheduled_for TIMESTAMP,
                executed_at TIMESTAMP,
                user_notes TEXT,
                system_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_post_id ON action_queue(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_status ON action_queue(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_scheduled ON action_queue(scheduled_for)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_actions_priority ON action_queue(priority DESC)")

        # PostMedia table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_media (
                media_id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                media_type TEXT NOT NULL,
                media_url TEXT NOT NULL,
                local_file_path TEXT,
                file_size INTEGER,
                mime_type TEXT,
                width INTEGER,
                height INTEGER,
                ai_analysis_status TEXT DEFAULT 'pending',
                ai_analysis TEXT,
                ai_analyzed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_post_id ON post_media(post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_analysis_status ON post_media(ai_analysis_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON post_media(media_type)")

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        conn.commit()
        print("✓ Schema created successfully")

    def migrate_posts(self, source_conn: sqlite3.Connection, dest_conn: sqlite3.Connection):
        """Migrate posts from old schema to new schema."""
        print("\nMigrating posts...")

        source_cursor = source_conn.cursor()
        dest_cursor = dest_conn.cursor()

        # Fetch all posts from source
        source_cursor.execute("""
            SELECT urn, full_urn, posted_at_timestamp, author_username,
                   text_content, json_data, first_seen_at, is_read, is_marked
            FROM posts
        """)

        posts = source_cursor.fetchall()
        self.stats["posts"]["total"] = len(posts)

        for post in posts:
            try:
                urn, full_urn, posted_at, author, text, json_data, first_seen, is_read, is_marked = post

                # Generate new AWS-style ID
                post_id = generate_aws_id(PREFIX_POST)

                # Extract additional fields from JSON
                platform = 'linkedin'
                post_type = None
                url = None

                if json_data:
                    try:
                        post_obj = json.loads(json_data)
                        post_type = post_obj.get('post_type', 'regular')
                        url = post_obj.get('url')
                    except json.JSONDecodeError:
                        pass

                # Insert into new posts table
                dest_cursor.execute("""
                    INSERT INTO posts (
                        post_id, urn, full_urn, platform, posted_at_timestamp,
                        author_username, text_content, post_type, url, raw_json,
                        first_seen_at, is_read, is_marked, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_id, urn, full_urn, platform, posted_at,
                    author, text, post_type, url, json_data,
                    first_seen, is_read, is_marked,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat()
                ))

                self.stats["posts"]["migrated"] += 1

            except Exception as e:
                print(f"Error migrating post {urn}: {e}")
                self.stats["posts"]["errors"] += 1

        dest_conn.commit()
        print(f"✓ Migrated {self.stats['posts']['migrated']}/{self.stats['posts']['total']} posts")

    def migrate_profiles(self, source_conn: sqlite3.Connection, dest_conn: sqlite3.Connection):
        """Migrate profiles from old schema to new schema."""
        print("\nMigrating profiles...")

        source_cursor = source_conn.cursor()
        dest_cursor = dest_conn.cursor()

        # Check if profiles table exists
        source_cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='profiles'
        """)

        if not source_cursor.fetchone():
            print("  No profiles table in source database, skipping")
            return

        # Fetch all profiles
        source_cursor.execute("""
            SELECT id, username, name, created_at, updated_at, is_active,
                   notes, post_count, last_synced_at
            FROM profiles
        """)

        profiles = source_cursor.fetchall()
        self.stats["profiles"]["total"] = len(profiles)

        for profile in profiles:
            try:
                old_id, username, name, created_at, updated_at, is_active, notes, post_count, last_synced = profile

                # Generate new AWS-style ID
                profile_id = generate_aws_id(PREFIX_PROFILE)

                # Store mapping for foreign key updates
                self.id_mapping["profiles"][old_id] = profile_id

                # Insert into new profiles table
                dest_cursor.execute("""
                    INSERT INTO profiles (
                        profile_id, username, name, platform, is_active, notes,
                        post_count, last_synced_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    profile_id, username, name, 'linkedin', is_active, notes,
                    post_count, last_synced, created_at, updated_at
                ))

                self.stats["profiles"]["migrated"] += 1

            except Exception as e:
                print(f"Error migrating profile {username}: {e}")
                self.stats["profiles"]["errors"] += 1

        dest_conn.commit()
        print(f"✓ Migrated {self.stats['profiles']['migrated']}/{self.stats['profiles']['total']} profiles")

    def migrate_tags(self, source_conn: sqlite3.Connection, dest_conn: sqlite3.Connection):
        """Migrate tags from old schema to new schema."""
        print("\nMigrating tags...")

        source_cursor = source_conn.cursor()
        dest_cursor = dest_conn.cursor()

        # Check if tags table exists
        source_cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='tags'
        """)

        if not source_cursor.fetchone():
            print("  No tags table in source database, skipping")
            return

        # Fetch all tags
        source_cursor.execute("SELECT id, name, color, created_at FROM tags")

        tags = source_cursor.fetchall()
        self.stats["tags"]["total"] = len(tags)

        for tag in tags:
            try:
                old_id, name, color, created_at = tag

                # Generate new AWS-style ID
                tag_id = generate_aws_id(PREFIX_TAG)

                # Store mapping for foreign key updates
                self.id_mapping["tags"][old_id] = tag_id

                # Insert into new tags table
                dest_cursor.execute("""
                    INSERT INTO tags (tag_id, name, description, color, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (tag_id, name, None, color, created_at))

                self.stats["tags"]["migrated"] += 1

            except Exception as e:
                print(f"Error migrating tag {name}: {e}")
                self.stats["tags"]["errors"] += 1

        dest_conn.commit()
        print(f"✓ Migrated {self.stats['tags']['migrated']}/{self.stats['tags']['total']} tags")

    def migrate_profile_tags(self, source_conn: sqlite3.Connection, dest_conn: sqlite3.Connection):
        """Migrate profile_tags from old schema to new schema."""
        print("\nMigrating profile_tags...")

        source_cursor = source_conn.cursor()
        dest_cursor = dest_conn.cursor()

        # Check if profile_tags table exists
        source_cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='profile_tags'
        """)

        if not source_cursor.fetchone():
            print("  No profile_tags table in source database, skipping")
            return

        # Fetch all profile_tags
        source_cursor.execute("SELECT id, profile_id, tag_id, created_at FROM profile_tags")

        profile_tags = source_cursor.fetchall()
        self.stats["profile_tags"]["total"] = len(profile_tags)

        for pt in profile_tags:
            try:
                old_id, old_profile_id, old_tag_id, created_at = pt

                # Generate new AWS-style ID
                profile_tag_id = generate_aws_id(PREFIX_PROFILE_TAG)

                # Map old IDs to new IDs
                new_profile_id = self.id_mapping["profiles"].get(old_profile_id)
                new_tag_id = self.id_mapping["tags"].get(old_tag_id)

                if not new_profile_id or not new_tag_id:
                    print(f"  Warning: Could not map profile_tag {old_id} (profile={old_profile_id}, tag={old_tag_id})")
                    self.stats["profile_tags"]["errors"] += 1
                    continue

                # Insert into new profile_tags table
                dest_cursor.execute("""
                    INSERT INTO profile_tags (profile_tag_id, profile_id, tag_id, created_at)
                    VALUES (?, ?, ?, ?)
                """, (profile_tag_id, new_profile_id, new_tag_id, created_at))

                self.stats["profile_tags"]["migrated"] += 1

            except Exception as e:
                print(f"Error migrating profile_tag {old_id}: {e}")
                self.stats["profile_tags"]["errors"] += 1

        dest_conn.commit()
        print(f"✓ Migrated {self.stats['profile_tags']['migrated']}/{self.stats['profile_tags']['total']} profile_tags")

    def validate_migration(self, dest_conn: sqlite3.Connection) -> bool:
        """Validate the migrated database."""
        print("\nValidating migration...")

        cursor = dest_conn.cursor()
        all_valid = True

        # Check posts
        cursor.execute("SELECT COUNT(*) FROM posts")
        post_count = cursor.fetchone()[0]
        print(f"  Posts: {post_count} records")

        if post_count != self.stats["posts"]["migrated"]:
            print(f"  ⚠ Warning: Expected {self.stats['posts']['migrated']} posts, found {post_count}")
            all_valid = False

        # Check profiles
        cursor.execute("SELECT COUNT(*) FROM profiles")
        profile_count = cursor.fetchone()[0]
        print(f"  Profiles: {profile_count} records")

        # Check tags
        cursor.execute("SELECT COUNT(*) FROM tags")
        tag_count = cursor.fetchone()[0]
        print(f"  Tags: {tag_count} records")

        # Check profile_tags
        cursor.execute("SELECT COUNT(*) FROM profile_tags")
        pt_count = cursor.fetchone()[0]
        print(f"  ProfileTags: {pt_count} records")

        # Check for orphaned foreign keys
        cursor.execute("""
            SELECT COUNT(*) FROM profile_tags pt
            LEFT JOIN profiles p ON pt.profile_id = p.profile_id
            WHERE p.profile_id IS NULL
        """)
        orphaned_profiles = cursor.fetchone()[0]
        if orphaned_profiles > 0:
            print(f"  ⚠ Warning: {orphaned_profiles} orphaned profile references in profile_tags")
            all_valid = False

        cursor.execute("""
            SELECT COUNT(*) FROM profile_tags pt
            LEFT JOIN tags t ON pt.tag_id = t.tag_id
            WHERE t.tag_id IS NULL
        """)
        orphaned_tags = cursor.fetchone()[0]
        if orphaned_tags > 0:
            print(f"  ⚠ Warning: {orphaned_tags} orphaned tag references in profile_tags")
            all_valid = False

        if all_valid:
            print("✓ Validation passed")
        else:
            print("⚠ Validation completed with warnings")

        return all_valid

    def run(self):
        """Execute the migration."""
        print("=" * 60)
        print("Database Migration: social-tui")
        print("=" * 60)
        print(f"Source: {self.source_db}")
        print(f"Output: {self.output_db}")
        print(f"Dry run: {self.dry_run}")
        print("=" * 60)

        # Check source database exists
        if not Path(self.source_db).exists():
            print(f"Error: Source database not found: {self.source_db}")
            sys.exit(1)

        # Don't overwrite existing output database
        if Path(self.output_db).exists() and not self.dry_run:
            response = input(f"\nOutput database {self.output_db} already exists. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print("Migration cancelled")
                sys.exit(0)
            Path(self.output_db).unlink()

        # Connect to databases
        source_conn = sqlite3.connect(self.source_db)
        source_conn.row_factory = sqlite3.Row

        if not self.dry_run:
            # Create output directory if needed
            Path(self.output_db).parent.mkdir(parents=True, exist_ok=True)
            dest_conn = sqlite3.connect(self.output_db)
            dest_conn.row_factory = sqlite3.Row
        else:
            # Use in-memory database for dry run
            dest_conn = sqlite3.connect(":memory:")
            dest_conn.row_factory = sqlite3.Row

        try:
            # Create new schema
            self.create_new_schema(dest_conn)

            # Migrate data
            self.migrate_posts(source_conn, dest_conn)
            self.migrate_profiles(source_conn, dest_conn)
            self.migrate_tags(source_conn, dest_conn)
            self.migrate_profile_tags(source_conn, dest_conn)

            # Validate
            self.validate_migration(dest_conn)

            # Print summary
            print("\n" + "=" * 60)
            print("Migration Summary")
            print("=" * 60)
            for entity, stats in self.stats.items():
                print(f"{entity.capitalize()}:")
                print(f"  Total: {stats['total']}")
                print(f"  Migrated: {stats['migrated']}")
                print(f"  Errors: {stats['errors']}")
            print("=" * 60)

            if self.dry_run:
                print("\n✓ Dry run completed successfully (no files written)")
            else:
                print(f"\n✓ Migration completed successfully")
                print(f"  Output database: {self.output_db}")

        except Exception as e:
            print(f"\n✗ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

        finally:
            source_conn.close()
            dest_conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate social-tui database to new schema")
    parser.add_argument("--source", default="data/posts.db", help="Source database path")
    parser.add_argument("--output", default="data/posts_v2.db", help="Output database path")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without writing files")

    args = parser.parse_args()

    migration = DatabaseMigration(
        source_db=args.source,
        output_db=args.output,
        dry_run=args.dry_run
    )

    migration.run()


if __name__ == "__main__":
    main()
