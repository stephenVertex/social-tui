#!/usr/bin/env python3
"""
Test script to verify Kitty image display works.
"""
import json
import glob
import sys
import base64
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlparse


def display_image_kitty(image_url: str):
    """Display an image using Kitty's icat or graphics protocol."""
    try:
        # Method 1: Try using icat command (most reliable for Kitty)
        try:
            # Try different icat command variations
            icat_cmd = None
            for cmd in ['kitty', 'icat', '/Applications/Kitty.app/Contents/MacOS/kitty']:
                try:
                    print(f"Trying command: {cmd}")
                    result = subprocess.run([cmd, '+icat' if cmd == 'kitty' else '--version'],
                                          capture_output=True,
                                          timeout=1)
                    if result.returncode == 0:
                        icat_cmd = [cmd, '+icat'] if cmd == 'kitty' else [cmd]
                        print(f"✓ Found working command: {' '.join(icat_cmd)}")
                        break
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    print(f"  - {cmd} not available: {e}")
                    continue

            if not icat_cmd:
                raise FileNotFoundError("No working icat command found")

            # Download image to temp file
            parsed = urlparse(image_url)
            if parsed.scheme in ('http', 'https'):
                print(f"Downloading image from: {image_url}")
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
            print(f"Image size: {len(image_data):,} bytes")
            print(f"Using command: {' '.join(icat_cmd)}\n")
            display_cmd = icat_cmd + ['--align', 'left', tmp_path]
            subprocess.run(display_cmd)

            # Clean up
            Path(tmp_path).unlink()
            print("\n✓ Image displayed successfully using icat")
            return

        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("icat command not available, trying graphics protocol...")
            pass

        # Method 2: Use Kitty graphics protocol directly
        parsed = urlparse(image_url)
        if parsed.scheme in ('http', 'https'):
            print(f"Downloading image from: {image_url}")
            with urlopen(image_url, timeout=10) as response:
                image_data = response.read()
        else:
            with open(image_url, 'rb') as f:
                image_data = f.read()

        print(f"Image size: {len(image_data):,} bytes")

        # Encode image as base64
        encoded = base64.standard_b64encode(image_data).decode('ascii')
        print(f"Encoded size: {len(encoded):,} chars")

        # Split into chunks
        chunk_size = 4096
        chunks = [encoded[i:i+chunk_size] for i in range(0, len(encoded), chunk_size)]
        print(f"Split into {len(chunks)} chunks")
        print("Transmitting using graphics protocol...\n")

        # Output Kitty graphics protocol escape sequences
        for i, chunk in enumerate(chunks):
            if i == 0:
                sys.stdout.buffer.write(f"\033_Ga=T,f=100;{chunk}\033\\".encode('ascii'))
            elif i == len(chunks) - 1:
                sys.stdout.buffer.write(f"\033_Gm=0;{chunk}\033\\".encode('ascii'))
            else:
                sys.stdout.buffer.write(f"\033_Gm=1;{chunk}\033\\".encode('ascii'))

        sys.stdout.buffer.flush()
        sys.stdout.write("\n")
        sys.stdout.flush()

        print("\n✓ Image transmission complete")
        print("\nIf you don't see the image above:")
        print("  • You may not be running in Kitty terminal")
        print("  • Try running this in the native Kitty app (not VSCode/Claude Code)")
        print("  • Install Kitty: brew install kitty")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        print(f"\nImage URL: {image_url}")
        print("You can open this URL in a browser to view the image.")


def main():
    # Load a sample post with an image
    posts = []
    for file_path in glob.glob("data/20251125/linkedin/*.json"):
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                posts.extend(data)

    # Find first post with an image
    img_post = next((p for p in posts if p.get('media', {}).get('type') == 'image'), None)

    if img_post:
        media = img_post.get('media', {})
        image_url = media.get('url')
        print(f"Found post with image")
        print(f"Author: {img_post.get('author', {}).get('username', 'N/A')}")
        print(f"Text preview: {img_post.get('text', '')[:100]}...")
        print(f"\nAttempting to display image...\n")
        display_image_kitty(image_url)
    else:
        print("No posts with images found")


if __name__ == "__main__":
    main()
