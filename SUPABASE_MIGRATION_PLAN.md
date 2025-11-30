# Supabase Migration Plan - Direct Approach

## Decision: Skip Abstraction Layer

We're migrating directly to Supabase without an abstraction layer for simplicity.

## Files to Migrate (7 files)

### Priority 1: Core Database Modules
These are the main files that need migration:

1. **`profile_manager.py`** - Profile CRUD operations
   - Functions: get_all_profiles, get_profile_by_id, create_profile, update_profile, delete_profile
   - Used by: profile_ui.py

2. **`tag_manager.py`** - Tag CRUD operations
   - Functions: get_all_tags, create_tag, add_profile_tag, get_profile_tags
   - Used by: profile_ui.py

3. **`manage_data.py`** - JSON import and stats
   - Core data import functionality
   - Stats calculation

4. **`interactive_posts.py`** - Post viewer queries
   - Main UI for viewing posts
   - Complex queries with filtering

### Priority 2: UI Layer
5. **`profile_ui.py`** - UI that calls the managers
   - May only need import updates if it uses the manager functions
   - Check if it has direct database calls

### Priority 3: Migration/Historical Scripts
6. **`migrate_historical_runs.py`** - Historical data import
   - One-time migration script
   - Low priority (can keep using SQLite or update later)

7. **`migrate_database.py`** - Database migration utilities
   - May not need changes (keeps SQLite→Supabase migration logic)

## Migration Pattern

### SQLite Pattern (OLD)
```python
import sqlite3

def get_posts(is_read=False):
    conn = sqlite3.connect('data/posts_v2.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM posts
        WHERE is_read = ?
        ORDER BY posted_at_timestamp DESC
    """, (is_read,))

    rows = cursor.fetchall()
    conn.close()
    return rows
```

### Supabase Pattern (NEW)
```python
from supabase_client import get_supabase_client

def get_posts(is_read=False):
    client = get_supabase_client()

    result = client.table('posts') \
        .select('*') \
        .eq('is_read', is_read) \
        .order('posted_at_timestamp', desc=True) \
        .execute()

    return result.data
```

## Common Conversions

### SELECT Queries
```python
# SQLite
cursor.execute("SELECT * FROM posts WHERE platform = ?", (platform,))
rows = cursor.fetchall()

# Supabase
result = client.table('posts').select('*').eq('platform', platform).execute()
rows = result.data
```

### INSERT Operations
```python
# SQLite
cursor.execute("""
    INSERT INTO posts (post_id, urn, text_content)
    VALUES (?, ?, ?)
""", (post_id, urn, text))
conn.commit()

# Supabase
client.table('posts').insert({
    'post_id': post_id,
    'urn': urn,
    'text_content': text
}).execute()
```

### UPDATE Operations
```python
# SQLite
cursor.execute("UPDATE posts SET is_read = ? WHERE post_id = ?", (True, post_id))
conn.commit()

# Supabase
client.table('posts').update({'is_read': True}).eq('post_id', post_id).execute()
```

### DELETE Operations
```python
# SQLite
cursor.execute("DELETE FROM posts WHERE post_id = ?", (post_id,))
conn.commit()

# Supabase
client.table('posts').delete().eq('post_id', post_id).execute()
```

### Complex Queries with JOINs
```python
# SQLite - JOIN query
cursor.execute("""
    SELECT p.*, pt.tag_id, t.name as tag_name
    FROM posts p
    LEFT JOIN post_tags pt ON p.post_id = pt.post_id
    LEFT JOIN tags t ON pt.tag_id = t.tag_id
    WHERE p.platform = ?
""", (platform,))

# Supabase - Use foreign key expansion
result = client.table('posts') \
    .select('*, post_tags(tag_id, tags(name))') \
    .eq('platform', platform) \
    .execute()
```

## Key Differences

| Aspect | SQLite | Supabase |
|--------|--------|----------|
| Connection | `sqlite3.connect()` per operation | Singleton client via `get_supabase_client()` |
| Queries | Raw SQL strings | Query builder methods |
| Parameters | `?` placeholders | Method parameters |
| Results | `cursor.fetchall()` returns tuples/dicts | `result.data` returns list of dicts |
| Commit | `conn.commit()` required | Auto-committed |
| Close | `conn.close()` required | Handled automatically |
| Transactions | Manual BEGIN/COMMIT | Use `.transaction()` context manager (if needed) |

## Migration Checklist

### For Each File:
- [ ] Replace `import sqlite3` with `from supabase_client import get_supabase_client`
- [ ] Remove all `sqlite3.connect('data/posts_v2.db')` calls
- [ ] Replace SQL queries with query builder methods
- [ ] Update function return types (tuples → dicts)
- [ ] Remove cursor and connection management
- [ ] Test all functions
- [ ] Update any calling code that expects different data structures

### Data Structure Changes:
- SQLite `cursor.fetchall()` returns: `[(col1, col2, ...), ...]` (tuples)
- Supabase `.execute().data` returns: `[{col1: val, col2: val, ...}, ...]` (dicts)

**Impact**: Code that accesses `row[0]` will need to change to `row['column_name']`

## Testing Strategy

1. **Migrate one file at a time**
2. **Test after each file** to ensure it works
3. **Start with simplest files** (tag_manager.py, profile_manager.py)
4. **Move to complex files** (interactive_posts.py)
5. **Keep SQLite database intact** as backup during migration

## Rollback Plan

- SQLite database stays at `data/posts_v2.db` (don't delete)
- Can revert code changes via git if needed
- Supabase data can be exported back to SQLite if necessary

## Next Steps

1. Start with `tag_manager.py` (simplest CRUD)
2. Then `profile_manager.py`
3. Then `manage_data.py`
4. Then `interactive_posts.py` (most complex)
5. Finally `profile_ui.py` (may only need import updates)
