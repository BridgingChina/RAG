#!/bin/bash
set -e

# Run database migration (idempotent — safe to run on every startup)
echo "Running database migration..."
python scripts/migrate_db.py

# Start the application
echo "Starting application..."
exec "$@"
