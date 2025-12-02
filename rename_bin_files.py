#!/usr/bin/env python3
"""
Rename .bin files to proper extensions based on their MIME type.
"""
from pathlib import Path
import subprocess

cache_dir = Path("cache/media/images")

# Get all .bin files
bin_files = list(cache_dir.glob("*.bin"))
print(f"Found {len(bin_files)} .bin files")

renamed = 0
for bin_file in bin_files:
    # Use 'file' command to detect type
    result = subprocess.run(
        ["file", "--mime-type", "-b", str(bin_file)],
        capture_output=True,
        text=True
    )
    mime_type = result.stdout.strip()

    # Map MIME type to extension
    ext_map = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'video/mp4': '.mp4',
    }

    new_ext = ext_map.get(mime_type, '.bin')

    if new_ext != '.bin':
        new_name = bin_file.with_suffix(new_ext)
        bin_file.rename(new_name)
        renamed += 1
        if renamed <= 5:  # Show first 5
            print(f"  ✓ {bin_file.name} → {new_name.name} ({mime_type})")

print(f"\n✓ Renamed {renamed} files")
