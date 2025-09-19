# scripts/test_db.py
import asyncpg
import asyncio

async def test_connection():
    try:
        conn = await asyncpg.connect('postgresql://ccv_user:ccv_pass@localhost:5432/ccv_db')
        print("✅ Database connected!")
        
        # Test query
        version = await conn.fetchval('SELECT version()')
        print(f"PostgreSQL version: {version}")
        
        await conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
