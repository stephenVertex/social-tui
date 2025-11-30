#!/bin/bash
# Script to link Supabase project using credentials from .env

# Load .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found"
    exit 1
fi

# Extract project ref from SUPABASE_URL
PROJECT_REF=$(echo $SUPABASE_URL | sed -E 's/.*\/\/([^.]+).*/\1/')

echo "Project ref: $PROJECT_REF"
echo "Linking Supabase project..."

# Link the project using DB_PASSWORD from .env
supabase link --project-ref "$PROJECT_REF" --password "$DB_PASSWORD"

if [ $? -eq 0 ]; then
    echo "✓ Successfully linked to Supabase project"
else
    echo "✗ Failed to link project"
    exit 1
fi
