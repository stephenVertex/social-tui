#!/usr/bin/env python3
"""
Diagnose missing media files from upload warnings.
"""
import sys
from pathlib import Path
from typing import List, Dict
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from supabase_client import get_supabase_client

# Missing media IDs from warnings
MISSING_MEDIA_IDS = [
    'pm-7e0ad730',
    'pm-36ee02af',
    'pm-c0a732b4',
    'pm-b6b63100',
    'pm-6b1be843',
    'pm-9abe9848',
    'pm-d63f4f57',
    'pm-b75c19a9',
    'pm-c39ca98c',
    'pm-2af1c0b5',
    'pm-944b7807',
    'pm-6f757dd9',
    'pm-c5c4d113',
    'pm-659a35f1',
]

def check_file_exists(path_str: str) -> bool:
    """Check if a file exists at the given path."""
    if not path_str:
        return False
    path = Path(path_str)
    return path.exists()


def search_for_file_by_name(filename: str, search_dirs: List[Path]) -> List[Path]:
    """Search for a file by name in multiple directories."""
    found = []
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for path in search_dir.rglob(filename):
            if path.is_file():
                found.append(path)
    return found


def diagnose_missing_media():
    """Query database and filesystem to diagnose missing media."""
    client = get_supabase_client()

    print("=" * 80)
    print("MISSING MEDIA DIAGNOSTICS")
    print("=" * 80)
    print(f"\nInvestigating {len(MISSING_MEDIA_IDS)} missing media records\n")

    # Query all missing media records
    result = client.table('post_media').select(
        'media_id, media_type, local_file_path, mime_type, archive_url, '
        'created_at, md5_sum, media_url, post_id'
    ).in_('media_id', MISSING_MEDIA_IDS).execute()

    media_records = result.data
    print(f"Found {len(media_records)} records in database\n")

    # Define search directories
    cache_root = Path('cache/media')
    search_dirs = [
        cache_root / 'images',
        cache_root / 'videos',
        cache_root / 'documents',
        cache_root,  # Also search root
    ]

    findings = {
        'file_exists_at_path': [],
        'file_found_elsewhere': [],
        'file_not_found': [],
        'no_path_info': [],
    }

    for record in media_records:
        media_id = record['media_id']
        local_path = record.get('local_file_path')
        md5_sum = record.get('md5_sum')
        media_url = record.get('media_url')
        post_id = record.get('post_id')

        print("-" * 80)
        print(f"Media ID: {media_id}")
        print(f"Post ID:  {post_id}")
        print(f"Type:     {record.get('media_type')}")
        print(f"MIME:     {record.get('mime_type')}")
        print(f"MD5:      {md5_sum}")
        print(f"Path:     {local_path}")
        print(f"URL:      {media_url}")

        # Check if file exists at recorded path
        if local_path:
            if check_file_exists(local_path):
                print(f"✓ File EXISTS at recorded path: {local_path}")
                findings['file_exists_at_path'].append({
                    'media_id': media_id,
                    'path': local_path
                })
                continue
            else:
                print(f"✗ File NOT FOUND at recorded path")

                # Try to find file by filename
                filename = Path(local_path).name
                print(f"  Searching for filename: {filename}")
                found_paths = search_for_file_by_name(filename, search_dirs)

                if found_paths:
                    print(f"  ✓ Found {len(found_paths)} file(s) with same name:")
                    for found_path in found_paths:
                        print(f"    - {found_path}")
                    findings['file_found_elsewhere'].append({
                        'media_id': media_id,
                        'expected_path': local_path,
                        'found_paths': [str(p) for p in found_paths]
                    })
                    continue
                else:
                    print(f"  ✗ File not found anywhere")
                    findings['file_not_found'].append({
                        'media_id': media_id,
                        'expected_path': local_path,
                        'media_url': media_url
                    })
        else:
            print(f"✗ No path information in database")
            findings['no_path_info'].append({
                'media_id': media_id,
                'media_url': media_url,
                'md5_sum': md5_sum
            })

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"File exists at recorded path:  {len(findings['file_exists_at_path'])}")
    print(f"File found elsewhere:          {len(findings['file_found_elsewhere'])}")
    print(f"File not found at all:         {len(findings['file_not_found'])}")
    print(f"No path information:           {len(findings['no_path_info'])}")
    print()

    # Recommendations
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    if findings['file_exists_at_path']:
        print(f"\n✓ {len(findings['file_exists_at_path'])} files exist - no action needed")

    if findings['file_found_elsewhere']:
        print(f"\n⚠ {len(findings['file_found_elsewhere'])} files found in wrong location:")
        print("  Action: Update local_file_path in database or move files")
        for item in findings['file_found_elsewhere']:
            print(f"    {item['media_id']}: {item['found_paths'][0]}")

    if findings['file_not_found']:
        print(f"\n✗ {len(findings['file_not_found'])} files completely missing:")
        print("  Action: Re-download from media_url or mark as unavailable")
        for item in findings['file_not_found']:
            print(f"    {item['media_id']}: {item.get('media_url', 'No URL')}")

    if findings['no_path_info']:
        print(f"\n✗ {len(findings['no_path_info'])} records have no path information:")
        print("  Action: Re-download from media_url or investigate posts")
        for item in findings['no_path_info']:
            print(f"    {item['media_id']}: {item.get('media_url', 'No URL')}")

    return findings


if __name__ == "__main__":
    try:
        findings = diagnose_missing_media()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
