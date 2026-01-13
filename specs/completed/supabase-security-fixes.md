# Supabase Security Fixes

**Completed:** 2025-01-13

## Summary

Fixed all Supabase security advisor errors and warnings for the social-tui project.

## Issues Fixed

### 1. SECURITY DEFINER Views (4 ERRORs)

**Problem:** Views were defined with SECURITY DEFINER property, which enforces RLS policies of the view creator rather than the querying user.

**Affected Views:**
- `public.v_post_engagement_history`
- `public.v_main_post_view`
- `public.post_engagement_history`
- `public.v_profiles_with_stats`

**Solution:** Set views to use SECURITY INVOKER instead:
```sql
ALTER VIEW public.post_engagement_history SET (security_invoker = on);
ALTER VIEW public.v_main_post_view SET (security_invoker = on);
ALTER VIEW public.v_post_engagement_history SET (security_invoker = on);
ALTER VIEW public.v_profiles_with_stats SET (security_invoker = on);
```

### 2. RLS Disabled on Tables (9 ERRORs)

**Problem:** Row Level Security was not enabled on public tables exposed to PostgREST.

**Affected Tables:**
- `public.data_downloads`
- `public.download_runs`
- `public.posts`
- `public.profiles`
- `public.profile_tags`
- `public.tags`
- `public.post_tags`
- `public.action_queue`
- `public.post_media`

**Solution:** Enabled RLS on all tables:
```sql
ALTER TABLE public.<table_name> ENABLE ROW LEVEL SECURITY;
```

### 3. Overly Permissive RLS Policies (9 WARNs)

**Problem:** Initial RLS policies used `FOR ALL` with `USING (true)` and `WITH CHECK (true)`, which the linter flags as overly permissive for write operations.

**Solution:** Split into granular policies:
- **SELECT policies** with `USING (true)` - acceptable for read access
- **INSERT policies** with `WITH CHECK (auth.role() = 'authenticated')`
- **UPDATE policies** with `USING (auth.role() = 'authenticated')` and `WITH CHECK (auth.role() = 'authenticated')`
- **DELETE policies** with `USING (auth.role() = 'authenticated')`

## Migrations Applied

1. `fix_security_definer_views` - Recreated views without SECURITY DEFINER
2. `enable_rls_on_all_tables` - Enabled RLS and created initial policies
3. `set_views_to_security_invoker` - Explicitly set security_invoker = on
4. `split_rls_policies_to_fix_warnings` - Replaced ALL policies with granular SELECT/INSERT/UPDATE/DELETE policies

## Final State

Security advisors now report **0 issues** (no errors or warnings).
