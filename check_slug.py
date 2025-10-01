import asyncio
from app.db import get_db
from sqlalchemy import text

async def check_polls():
    async for db in get_db():
        result = await db.execute(
            text("SELECT short_id, slug, owner_email, title FROM polls ORDER BY created_at DESC LIMIT 5")
        )
        rows = result.fetchall()
        
        print("\nRecent polls:")
        print("-" * 80)
        for row in rows:
            print(f"Short ID: {row[0]}")
            print(f"Slug: {row[1] if row[1] else 'NULL'}")
            print(f"Owner: {row[2] if row[2] else 'NULL'}")
            print(f"Title: {row[3]}")
            print("-" * 80)
        break

asyncio.run(check_polls())
