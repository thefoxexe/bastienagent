import os
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


async def init_db():
    global _pool
    if DATABASE_URL:
        import asyncpg
        _pool = await asyncpg.create_pool(DATABASE_URL)
        async with _pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    done INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    done_at TIMESTAMPTZ
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
    else:
        import aiosqlite
        async with aiosqlite.connect("bastien.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    done INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    done_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            await db.commit()


async def add_task(title: str) -> int:
    if _pool:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("INSERT INTO tasks (title) VALUES ($1) RETURNING id", title)
            return row["id"]
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        cursor = await db.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
        await db.commit()
        return cursor.lastrowid


async def list_tasks(include_done: bool = False) -> list[dict]:
    if _pool:
        async with _pool.acquire() as conn:
            if include_done:
                rows = await conn.fetch("SELECT id, title, done FROM tasks ORDER BY created_at DESC")
            else:
                rows = await conn.fetch("SELECT id, title, done FROM tasks WHERE done = 0 ORDER BY created_at DESC")
            return [dict(r) for r in rows]
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        db.row_factory = aiosqlite.Row
        if include_done:
            cursor = await db.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        else:
            cursor = await db.execute("SELECT * FROM tasks WHERE done = 0 ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def complete_task(task_id: int) -> bool:
    if _pool:
        async with _pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE tasks SET done = 1, done_at = NOW() WHERE id = $1 AND done = 0", task_id
            )
            return int(result.split()[-1]) > 0
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        cursor = await db.execute(
            "UPDATE tasks SET done = 1, done_at = ? WHERE id = ? AND done = 0",
            (datetime.now().isoformat(), task_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_task(task_id: int) -> bool:
    if _pool:
        async with _pool.acquire() as conn:
            result = await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
            return int(result.split()[-1]) > 0
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        cursor = await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return cursor.rowcount > 0


async def add_note(content: str) -> int:
    if _pool:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("INSERT INTO notes (content) VALUES ($1) RETURNING id", content)
            return row["id"]
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        cursor = await db.execute("INSERT INTO notes (content) VALUES (?)", (content,))
        await db.commit()
        return cursor.lastrowid


async def list_notes(limit: int = 10) -> list[dict]:
    if _pool:
        async with _pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, content FROM notes ORDER BY created_at DESC LIMIT $1", limit)
            return [dict(r) for r in rows]
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_note(note_id: int) -> bool:
    if _pool:
        async with _pool.acquire() as conn:
            result = await conn.execute("DELETE FROM notes WHERE id = $1", note_id)
            return int(result.split()[-1]) > 0
    import aiosqlite
    async with aiosqlite.connect("bastien.db") as db:
        cursor = await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await db.commit()
        return cursor.rowcount > 0
