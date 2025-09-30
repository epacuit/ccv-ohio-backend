#!/bin/bash
# reset_db_clean.sh - Complete database reset: drop tables AND clean migrations

set -e  # Exit on any error

echo "WARNING: This will completely reset your database and migrations!"
read -p "Type 'RESET' to confirm: " confirm

if [ "$confirm" != "RESET" ]; then
    echo "Reset cancelled"
    exit 1
fi

echo "Starting complete database reset..."

# Step 1: Drop ALL tables including alembic_version using Python
echo "Dropping all database tables (including alembic_version)..."
python3 - << 'EOF'
import asyncio
import sys
from sqlalchemy import text

async def drop_everything():
    try:
        from app.db import engine
        # Import ALL models to ensure they're registered
        from app.models import Base, Poll, Ballot, Result, Voter
        
        print("  - Dropping all tables and alembic_version...")
        async with engine.begin() as conn:
            # Drop alembic_version table specifically
            await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
            # Drop all other tables
            await conn.run_sync(Base.metadata.drop_all)
        print("  - All tables dropped")
        
    except Exception as e:
        print(f"  - Error: {e}")
        sys.exit(1)

asyncio.run(drop_everything())
EOF

# Step 2: Remove all existing migration files
echo "Removing old migration files..."
rm -rf migrations/versions/*

# Step 3: Ensure all models are imported in the models __init__.py
echo "Ensuring all models are imported..."
python3 - << 'EOF'
import sys
import os

# Check if models/__init__.py imports the Voter model
init_file = "app/models/__init__.py"
if os.path.exists(init_file):
    with open(init_file, 'r') as f:
        content = f.read()
    
    if 'Voter' not in content:
        print("  - Adding Voter import to models/__init__.py")
        with open(init_file, 'a') as f:
            f.write("\nfrom .voter import Voter\n")
    else:
        print("  - Voter model already imported")
else:
    print(f"  - Warning: {init_file} not found")
EOF

# Step 4: Create fresh initial migration
echo "Creating new initial migration..."
alembic revision --autogenerate -m "Initial migration with all models"

# Step 5: Apply the migration
echo "Applying migration..."
alembic upgrade head

echo ""
echo "✓ Database reset complete!"
echo "✓ Migration history clean"
echo "✓ All tables created (including voters)"
echo "✓ Ready to start your server"