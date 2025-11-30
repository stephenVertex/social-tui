# Social TUI - Setup Guide

**Database**: Supabase (PostgreSQL)
**Language**: Python 3.13+
**UI Framework**: Textual

## Quick Start

### 1. Clone and Install

```bash
git clone <repository-url>
cd social-tui
```

### 2. Configure Supabase Credentials

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your Supabase credentials
# Get credentials from: https://supabase.com/dashboard
```

Required environment variables:
- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_API_KEY` - Your anon/public API key
- `SUPABASE_DB_URL` - Database connection string (for CLI)
- `DB_PASSWORD` - Database password

### 3. Install Dependencies

```bash
# Install uv if not already installed
# curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv pip install -e .
```

### 4. Run the Application

```bash
# Interactive post viewer
uv run python interactive_posts.py

# Profile management
uv run python profile_ui.py

# Import data from JSON files
uv run python manage_data.py import <directory>

# View database statistics
uv run python manage_data.py stats
```

## Features

### Multi-Computer Synchronization
✅ All data syncs automatically via Supabase
✅ Changes on one computer appear immediately on others
✅ No manual syncing required

### Core Functionality
- **Post Management**: View, filter, mark posts as read
- **Profile Tracking**: Manage profiles with tagging
- **Engagement Metrics**: Time-series data tracking
- **Tag Organization**: Categorize profiles with tags
- **Data Import**: Bulk import from JSON files

## Architecture

### Database Schema
- **9 tables** with foreign key relationships
- **AWS-style IDs** (e.g., `tag-a1b2c3d4`, `prf-07f60651`)
- **Time-series tracking** for engagement history
- **JSON storage** for raw data preservation

### Files
- `supabase_client.py` - Database connection singleton
- `tag_manager.py` - Tag CRUD operations
- `profile_manager.py` - Profile CRUD operations
- `interactive_posts.py` - Main post viewer UI
- `profile_ui.py` - Profile management UI
- `manage_data.py` - Data import CLI tool

## Database Schema

The application uses 9 tables:

1. **posts** - Social media posts (1,070 rows)
2. **profiles** - User profiles (28 rows)
3. **tags** - Organization tags (5 rows)
4. **profile_tags** - Profile-tag associations (43 rows)
5. **post_tags** - Post-tag associations
6. **data_downloads** - Time-series engagement data (1,880 rows)
7. **download_runs** - Import run metadata (6 rows)
8. **action_queue** - Queued actions
9. **post_media** - Media attachments

## Migration from SQLite

This project recently migrated from SQLite to Supabase. See:
- `specs/supabase_migration.md` - Complete migration documentation
- `PHASE6_TEST_RESULTS.md` - Validation test results
- `data/BACKUP_README.md` - SQLite backup information

## Troubleshooting

### Connection Issues
- Verify `.env` file has correct credentials
- Check Supabase project is active
- Ensure you're within free tier limits (500MB database)

### Import Errors
- Ensure JSON files are in correct format
- Check for duplicate URNs (will be skipped)
- Review error messages for specific issues

### Performance
- All queries should complete in < 500ms
- Large imports are batched (100 rows at a time)
- Indexes are optimized for common queries

## Development

### Testing
```bash
# Run comprehensive validation
uv run python test_phase6_validation.py

# Run UI component tests
uv run python test_ui_validation.py

# Verify data migration
uv run python verify_migration.py
```

### Database Migrations
```bash
# Link Supabase project
./link_supabase.sh

# Create new migration
supabase migration new <migration_name>

# Apply migrations
supabase db push
```

## Support

For issues or questions:
- Review `specs/supabase_migration.md` for detailed documentation
- Check test files for usage examples
- Consult Supabase docs: https://supabase.com/docs
