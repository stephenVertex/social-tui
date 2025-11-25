#!/usr/bin/env python3
"""
Test if kitty's icat command is available and can display images.
"""
import subprocess
import sys
import tempfile
import json
import glob
from urllib.request import urlopen
from pathlib import Path


def test_icat_available():
    """Check if icat command is available."""
    try:
        result = subprocess.run(['icat', '--version'],
                              capture_output=True,
                              text=True,
                              timeout=2)
        print(f"✓ icat is available: {result.stdout.strip()}")
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("✗ icat command not found")
        print("  Install it with: brew install kitty (or your package manager)")
        return False


def display_image_with_icat(image_url: str):
    """Display image using icat command."""
    try:
        # Download image to temp file
        print(f"Downloading: {image_url}")
        with urlopen(image_url, timeout=10) as response:
            image_data = response.read()

        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=False) as tmp:
            tmp.write(image_data)
            tmp_path = tmp.name

        print(f"Saved to: {tmp_path}")
        print(f"Image size: {len(image_data)} bytes\n")

        # Display with icat
        subprocess.run(['icat', '--align', 'left', tmp_path])

        # Clean up
        Path(tmp_path).unlink()

        print("\n✓ Image displayed successfully")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("Kitty Image Display Test")
    print("=" * 60)
    print()

    if not test_icat_available():
        sys.exit(1)

    print()

    # Load sample post with image
    posts = []
    for file_path in glob.glob("data/20251125/linkedin/*.json"):
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                posts.extend(data)

    img_post = next((p for p in posts if p.get('media', {}).get('type') == 'image'), None)

    if img_post:
        media = img_post.get('media', {})
        image_url = media.get('url')
        author = img_post.get('author', {}).get('username', 'N/A')

        print(f"Test post:")
        print(f"  Author: {author}")
        print(f"  Text: {img_post.get('text', '')[:80]}...")
        print()

        display_image_with_icat(image_url)
    else:
        print("No posts with images found")


if __name__ == "__main__":
    main()
