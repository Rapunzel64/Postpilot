"""Background post scheduler and database manager for PostPilot.
Handles scheduled queue persistence (SQLite / MongoDB), auto-posting daemon, and LinkedIn credential storage.
"""
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
import linkedin_api

logger = logging.getLogger("postpilot.scheduler")

_scheduler_started = False
_scheduler_lock = threading.Lock()


class PostScheduler:
    def __init__(self, db_file: Path, use_mongo: bool = False, mongo_uri: str = "", mongo_db: str = "postpilot"):
        self.db_file = db_file
        self.use_mongo = use_mongo
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self._init_db()

    def _get_mongo(self):
        from pymongo import MongoClient
        client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=8000)
        return client[self.mongo_db]

    def _get_lite(self):
        con = sqlite3.connect(self.db_file, check_same_thread=False, timeout=20)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        if self.use_mongo:
            try:
                db = self._get_mongo()
                db.user_settings.create_index("username", unique=True)
                db.scheduled_posts.create_index([("username", 1), ("scheduled_time", 1)])
                db.scheduled_posts.create_index([("status", 1), ("scheduled_time", 1)])
            except Exception as e:
                logger.error(f"Error initializing MongoDB scheduled collections: {e}")
        else:
            con = self._get_lite()
            try:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        username TEXT PRIMARY KEY,
                        linkedin_token TEXT,
                        linkedin_author TEXT,
                        linkedin_name TEXT,
                        updated REAL
                    )
                """)
                con.execute("""
                    CREATE TABLE IF NOT EXISTS scheduled_posts (
                        id TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        topic TEXT,
                        post TEXT NOT NULL,
                        img TEXT,
                        svg TEXT,
                        scheduled_time REAL NOT NULL,
                        status TEXT NOT NULL,
                        error_msg TEXT,
                        created_at REAL,
                        published_at REAL,
                        linkedin_urn TEXT
                    )
                """)
                con.execute("CREATE INDEX IF NOT EXISTS sched_user ON scheduled_posts(username)")
                con.execute("CREATE INDEX IF NOT EXISTS sched_status_time ON scheduled_posts(status, scheduled_time)")
                con.commit()
            finally:
                con.close()

    # User LinkedIn credentials
    def save_user_linkedin(self, username: str, token: str, author_urn: str = "", name: str = ""):
        now = time.time()
        if self.use_mongo:
            db = self._get_mongo()
            db.user_settings.update_one(
                {"username": username},
                {"$set": {
                    "username": username,
                    "linkedin_token": token,
                    "linkedin_author": author_urn,
                    "linkedin_name": name,
                    "updated": now
                }},
                upsert=True
            )
        else:
            con = self._get_lite()
            try:
                con.execute(
                    "INSERT OR REPLACE INTO user_settings (username, linkedin_token, linkedin_author, linkedin_name, updated) VALUES (?,?,?,?,?)",
                    (username, token, author_urn, name, now)
                )
                con.commit()
            finally:
                con.close()

    def get_user_linkedin(self, username: str) -> Dict:
        if self.use_mongo:
            db = self._get_mongo()
            doc = db.user_settings.find_one({"username": username}, {"_id": 0})
            return doc or {}
        con = self._get_lite()
        try:
            cur = con.execute("SELECT linkedin_token, linkedin_author, linkedin_name FROM user_settings WHERE username=?", (username,))
            row = cur.fetchone()
            if row:
                return {
                    "linkedin_token": row["linkedin_token"],
                    "linkedin_author": row["linkedin_author"],
                    "linkedin_name": row["linkedin_name"]
                }
            return {}
        finally:
            con.close()

    def clear_user_linkedin(self, username: str):
        if self.use_mongo:
            db = self._get_mongo()
            db.user_settings.delete_one({"username": username})
        else:
            con = self._get_lite()
            try:
                con.execute("DELETE FROM user_settings WHERE username=?", (username,))
                con.commit()
            finally:
                con.close()

    # Scheduling
    def schedule_post(self, username: str, topic: str, post: str, img: str = "", svg: str = "", scheduled_time: float = 0) -> str:
        import secrets
        post_id = f"sched_{int(time.time())}_{secrets.token_hex(3)}"
        now = time.time()
        # Keep stored image within reasonable limits
        stored_img = img if len(img) <= 600000 else ""

        if self.use_mongo:
            db = self._get_mongo()
            db.scheduled_posts.insert_one({
                "_id": post_id,
                "id": post_id,
                "username": username,
                "topic": topic,
                "post": post,
                "img": stored_img,
                "svg": svg,
                "scheduled_time": scheduled_time,
                "status": "scheduled",
                "error_msg": "",
                "created_at": now,
                "published_at": None,
                "linkedin_urn": ""
            })
        else:
            con = self._get_lite()
            try:
                con.execute(
                    "INSERT INTO scheduled_posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (post_id, username, topic, post, stored_img, svg, scheduled_time, "scheduled", "", now, None, "")
                )
                con.commit()
            finally:
                con.close()
        return post_id

    def get_user_scheduled_posts(self, username: str, limit: int = 50) -> List[Dict]:
        if self.use_mongo:
            db = self._get_mongo()
            cursor = db.scheduled_posts.find({"username": username}).sort("scheduled_time", 1).limit(limit)
            res = []
            for d in cursor:
                d["id"] = d.get("_id", d.get("id"))
                res.append(d)
            return res
        con = self._get_lite()
        try:
            cur = con.execute(
                "SELECT id, username, topic, post, img, svg, scheduled_time, status, error_msg, created_at, published_at, linkedin_urn FROM scheduled_posts WHERE username=? ORDER BY scheduled_time ASC LIMIT ?",
                (username, limit)
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            con.close()

    def delete_scheduled_post(self, username: str, post_id: str):
        if self.use_mongo:
            db = self._get_mongo()
            db.scheduled_posts.delete_one({"_id": post_id, "username": username})
        else:
            con = self._get_lite()
            try:
                con.execute("DELETE FROM scheduled_posts WHERE id=? AND username=?", (post_id, username))
                con.commit()
            finally:
                con.close()

    def update_post_status(self, post_id: str, status: str, error_msg: str = "", published_at: Optional[float] = None, linkedin_urn: str = ""):
        if self.use_mongo:
            db = self._get_mongo()
            db.scheduled_posts.update_one(
                {"_id": post_id},
                {"$set": {
                    "status": status,
                    "error_msg": error_msg,
                    "published_at": published_at,
                    "linkedin_urn": linkedin_urn
                }}
            )
        else:
            con = self._get_lite()
            try:
                con.execute(
                    "UPDATE scheduled_posts SET status=?, error_msg=?, published_at=?, linkedin_urn=? WHERE id=?",
                    (status, error_msg, published_at, linkedin_urn, post_id)
                )
                con.commit()
            finally:
                con.close()

    def get_due_posts(self) -> List[Dict]:
        now = time.time()
        if self.use_mongo:
            db = self._get_mongo()
            cursor = db.scheduled_posts.find({"status": "scheduled", "scheduled_time": {"$lte": now}})
            res = []
            for d in cursor:
                d["id"] = d.get("_id", d.get("id"))
                res.append(d)
            return res
        con = self._get_lite()
        try:
            cur = con.execute(
                "SELECT id, username, topic, post, img, svg, scheduled_time, status, error_msg, created_at FROM scheduled_posts WHERE status='scheduled' AND scheduled_time <= ?",
                (now,)
            )
            return [dict(row) for row in cur.fetchall()]
        finally:
            con.close()

    def execute_single_post(self, post_item: Dict, override_token: Optional[str] = None) -> Dict:
        """Executes a single post to LinkedIn."""
        username = post_item.get("username")
        post_id = post_item.get("id")
        post_text = post_item.get("post", "")
        img_str = post_item.get("img", "")

        token = override_token
        author_urn = None

        if not token:
            creds = self.get_user_linkedin(username)
            token = creds.get("linkedin_token")
            author_urn = creds.get("linkedin_author")

        if not token:
            import os
            token = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()

        if not token:
            err = "No LinkedIn access token found for user. Please connect your LinkedIn account."
            self.update_post_status(post_id, "failed", error_msg=err)
            return {"success": False, "error": err}

        image_bytes, mime = linkedin_api.extract_image_bytes(img_str) if img_str else (None, None)

        res = linkedin_api.publish_post(
            token=token,
            text=post_text,
            image_bytes=image_bytes,
            mime_type=mime or "image/jpeg",
            author_urn=author_urn
        )

        now = time.time()
        if res.get("success"):
            self.update_post_status(
                post_id=post_id,
                status="published",
                error_msg="",
                published_at=now,
                linkedin_urn=res.get("post_id", "")
            )
            return {"success": True, "post_id": res.get("post_id", "")}
        else:
            err = res.get("error", "Unknown error uploading to LinkedIn")
            self.update_post_status(
                post_id=post_id,
                status="failed",
                error_msg=err,
                published_at=now
            )
            return {"success": False, "error": err}

    def process_due_queue(self):
        due = self.get_due_posts()
        for item in due:
            try:
                self.execute_single_post(item)
            except Exception as e:
                logger.error(f"Error processing scheduled post {item.get('id')}: {e}")
                self.update_post_status(item.get("id"), "failed", error_msg=str(e))


def run_scheduler_daemon(scheduler_instance: PostScheduler):
    """Background daemon loop that checks for due posts every 20 seconds."""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True

    def _loop():
        while True:
            try:
                scheduler_instance.process_due_queue()
            except Exception as e:
                logger.error(f"Scheduler exception in daemon loop: {e}")
            time.sleep(20)

    t = threading.Thread(target=_loop, daemon=True, name="PostPilotSchedulerDaemon")
    t.start()
    return t
