#!/usr/bin/env python3
"""
check_scheduled_emissions.py — Auto-publish scheduled blog drafts.

Runs on the Debian PC via cron every 15 minutes.
Checks json/blog_drafts.json for posts with a 'scheduled' time that has
passed and publishes them automatically.

Cron entry (*/15 * * * *):
    */15 * * * * cd ~/dirtiestships-website && ~/ship-registry/venv/bin/python3 check_scheduled_emissions.py >> /tmp/check_scheduled_emissions.log 2>&1
"""

import os
import json
import subprocess
from datetime import datetime

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DRAFTS_DIR  = os.path.join(BASE_DIR, "blog", "posts", "drafts")
POSTS_DIR   = os.path.join(BASE_DIR, "blog", "posts")
BLOG_DRAFTS = os.path.join(BASE_DIR, "json", "blog_drafts.json")
BLOG_JSON   = os.path.join(BASE_DIR, "json", "blog.json")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def publish(meta: dict):
    slug = meta["slug"]
    src  = os.path.join(DRAFTS_DIR, f"{slug}.md")
    dst  = os.path.join(POSTS_DIR,  f"{slug}.md")

    if not os.path.exists(src):
        print(f"  SKIP (no .md file): {slug}")
        return False

    with open(src, encoding="utf-8") as f:
        content = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)
    os.remove(src)

    # Add to blog.json
    published = load_json(BLOG_JSON, {"posts": []})
    entry = {
        "slug":    meta["slug"],
        "title":   meta["title"],
        "date":    meta["date"],
        "excerpt": meta.get("excerpt", ""),
        "author":  meta.get("author", "DirtiestShips"),
    }
    if meta.get("featured_image"):
        entry["featured_image"] = meta["featured_image"]
    if meta.get("source_url"):
        entry["source_url"] = meta["source_url"]
    published["posts"].insert(0, entry)
    save_json(BLOG_JSON, published)

    # Remove from blog_drafts.json
    drafts = load_json(BLOG_DRAFTS, {"posts": []})
    drafts["posts"] = [p for p in drafts["posts"] if p["slug"] != slug]
    save_json(BLOG_DRAFTS, drafts)

    return True


def git_push(slug: str):
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        "ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no"
    )
    try:
        subprocess.run(
            ["git", "pull", "--no-rebase"],
            check=True, cwd=BASE_DIR, env=env, capture_output=True,
        )
        subprocess.run(
            ["git", "add",
             f"blog/posts/{slug}.md",
             "blog/posts/drafts/",
             "json/blog.json",
             "json/blog_drafts.json"],
            check=True, cwd=BASE_DIR, env=env,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Auto-publish scheduled post: {slug}"],
            check=True, cwd=BASE_DIR, env=env,
        )
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR, env=env)
        print(f"  Pushed: {slug}")
    except subprocess.CalledProcessError as e:
        print(f"  Git error: {e}")


def main():
    now = datetime.now()
    drafts = load_json(BLOG_DRAFTS, {"posts": []})
    published_any = False

    for meta in list(drafts.get("posts", [])):
        scheduled = meta.get("scheduled")
        if not scheduled:
            continue
        try:
            scheduled_dt = datetime.strptime(scheduled, "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        if now >= scheduled_dt:
            print(f"{now.strftime('%Y-%m-%d %H:%M')} Publishing: {meta['slug']}")
            if publish(meta):
                git_push(meta["slug"])
                published_any = True

    if not published_any:
        print(f"{now.strftime('%Y-%m-%d %H:%M')} No scheduled posts due.")


if __name__ == "__main__":
    main()
