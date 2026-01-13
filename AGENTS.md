# Agent Instructions

## Supabase Security Best Practices

When working with Supabase databases, follow these guidelines to avoid security linter warnings:

### Views

- **Never use SECURITY DEFINER** on views unless absolutely necessary
- After creating a view, explicitly set it to use SECURITY INVOKER:
  ```sql
  ALTER VIEW public.my_view SET (security_invoker = on);
  ```
- SECURITY DEFINER views bypass RLS for the querying user, which is a security risk

### Row Level Security (RLS)

- **Always enable RLS** on all public tables:
  ```sql
  ALTER TABLE public.my_table ENABLE ROW LEVEL SECURITY;
  ```

### RLS Policies

- **Do not use `FOR ALL` policies with `USING (true)`** - the linter flags this as overly permissive
- Instead, create **separate policies for each operation**:

  ```sql
  -- SELECT: USING (true) is acceptable for read access
  CREATE POLICY "Allow select for authenticated" ON public.my_table
    FOR SELECT TO authenticated USING (true);

  -- INSERT: Use explicit auth check
  CREATE POLICY "Allow insert for authenticated" ON public.my_table
    FOR INSERT TO authenticated WITH CHECK (auth.role() = 'authenticated');

  -- UPDATE: Use explicit auth check for both USING and WITH CHECK
  CREATE POLICY "Allow update for authenticated" ON public.my_table
    FOR UPDATE TO authenticated
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

  -- DELETE: Use explicit auth check
  CREATE POLICY "Allow delete for authenticated" ON public.my_table
    FOR DELETE TO authenticated USING (auth.role() = 'authenticated');
  ```

- For multi-tenant apps, replace `auth.role() = 'authenticated'` with user-specific checks like `auth.uid() = user_id`

### Checking Security Status

Use the Supabase MCP tool to check for security issues:
```
mcp__supabase__get_advisors with type: "security"
```

Run this after making DDL changes to catch issues early.
