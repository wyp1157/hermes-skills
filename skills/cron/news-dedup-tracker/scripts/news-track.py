#!/usr/bin/env python3
"""Track pushed news for deduplication. Usage:
  python3 news-track.py check <title> <url>     # Check if news already pushed
  python3 news-track.py record <json_list>       # Record new items (JSON array string)
"""
import json
import sys
import os
from datetime import datetime

HISTORY_FILE = os.path.expanduser('~/.hermes/data/news_history.json')
MAX_ENTRIES = 200

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE) as f:
        return json.load(f)

def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def check_duplicate(title, url):
    """Check if news is already in history. Returns True if duplicate."""
    history = load_history()
    title = title.strip().lower()
    url = url.strip().lower()
    for item in history:
        if item.get('url', '').lower() == url:
            return True
        if item.get('title', '').lower() == title:
            return True
    return False

def record(items_json):
    """Record new items from JSON array string."""
    try:
        new_items = json.loads(items_json)
        if not isinstance(new_items, list):
            new_items = [new_items]
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON: {items_json[:100]}")
        sys.exit(1)
    
    history = load_history()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    for item in new_items:
        item['pushed_at'] = now
        # Skip if already exists
        duplicate = False
        for existing in history:
            if existing.get('url') == item.get('url'):
                duplicate = True
                break
            if existing.get('title') == item.get('title'):
                duplicate = True
                break
        if not duplicate:
            history.append(item)
    
    # Trim oldest
    history = history[-MAX_ENTRIES:]
    save_history(history)
    print(f"OK: recorded {len(new_items)} items, history now {len(history)} entries")

def list_history(limit=10):
    """Show most recent entries."""
    history = load_history()
    if not history:
        print("History is empty")
        return
    for item in history[-limit:]:
        print(f"[{item.get('pushed_at','?')}] {item.get('title','?')}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: news-track.py check|record|list")
        sys.exit(1)
    
    action = sys.argv[1]
    if action == 'check':
        if len(sys.argv) < 4:
            print("Usage: news-track.py check <title> <url>")
            sys.exit(1)
        dup = check_duplicate(sys.argv[2], sys.argv[3])
        print("DUPLICATE" if dup else "NEW")
    elif action == 'record':
        if len(sys.argv) < 3:
            # Read from stdin
            record(sys.stdin.read())
        else:
            record(sys.argv[2])
    elif action == 'list':
        list_history()
    else:
        print(f"Unknown action: {action}")
