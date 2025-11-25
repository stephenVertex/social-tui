# Kitty Image Display Feature

## ⚠️ Important Limitation

**The Kitty graphics protocol only works when running directly in the Kitty terminal application.** It will NOT work in:
- VSCode's integrated terminal
- Claude Code's terminal
- iTerm2, Terminal.app, or other terminal emulators
- tmux/screen (without special configuration)

The escape sequences you see in the terminal output (like `_Ga=T,f=100;...`) are Kitty's graphics protocol commands that only Kitty terminal understands.

## Requirements

1. **Kitty Terminal Application**: You must launch and run the script in the Kitty app itself
   - Download: https://sw.kovidgoyal.net/kitty/
   - Install: `brew install --cask kitty`
   - Launch: `open -a Kitty` or find it in Applications

2. **icat Command** (bundled with Kitty): Command-line image display tool
   - Comes with Kitty installation
   - Located in: `/Applications/Kitty.app/Contents/MacOS/kitty`
   - Test: `icat --version`

## Important: Where to Run

❌ **Won't work in:**
- VSCode's integrated terminal
- Claude Code's terminal
- iTerm2
- Terminal.app
- tmux (without special configuration)
- SSH sessions (without X11 forwarding)

✅ **Will work in:**
- Native Kitty terminal application
- Kitty running locally on your machine

## Usage

### 1. Open Kitty Terminal

Launch the Kitty terminal application (not any other terminal).

### 2. Run the Interactive Viewer

```bash
# Navigate to the project directory
cd /Users/stephen/dev/apify-incoming-linkedin

# Run with Kitty image support
uv run python interactive_posts.py --kitty-images
```

### 3. View Images

1. Browse posts - posts with images show a 📷 indicator
2. Press `Enter` on a post with an image to see details
3. In the detail view, press `i` to display the image
4. The app will suspend and show the image
5. Press `Enter` to return to the app

## Testing

### Test icat Command

```bash
# Check if icat is available
icat --version

# Test with sample image
uv run python test_icat.py
```

### Test Graphics Protocol

```bash
# Test the raw Kitty graphics protocol
uv run python test_kitty_image.py
```

## Troubleshooting

### "icat command not found"

Install Kitty terminal:
```bash
brew install kitty
```

Make sure Kitty's bin directory is in your PATH:
```bash
export PATH="/Applications/Kitty.app/Contents/MacOS:$PATH"
```

### Images don't display

1. Verify you're in the actual Kitty terminal app
2. Check that graphics protocol is enabled in Kitty config:
   ```
   # ~/.config/kitty/kitty.conf
   # This should be enabled by default
   ```

3. Try opening Kitty directly:
   ```bash
   # From Finder: Applications > Kitty
   # Or from command line:
   open -a Kitty
   ```

### Image URL as fallback

If images can't be displayed, the URL will be shown so you can:
- Copy the URL
- Open it in a browser to view the image

## How It Works

The implementation uses two methods:

1. **icat command** (preferred): Uses Kitty's built-in image display command
   - More reliable
   - Better compatibility
   - Handles various image formats

2. **Graphics protocol** (fallback): Direct escape sequence transmission
   - Used if icat is not available
   - May not work in all environments
   - Requires specific terminal support

## Alternative: Browser-based Viewing

If Kitty terminal is not available, you can:

1. View post details to see the image URL
2. Copy the URL
3. Paste into a web browser

This is automatically suggested if image display fails.
