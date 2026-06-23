---
name: news-dedup-tracker
description: "Persistent file-based news dedup for cron jobs that push breaking news. Tracks pushed headlines + URLs to eliminate repeat pushes. Use when setting up or fixing news cron tasks, or when user says 重复的新闻不用再次推送, news duplicate, dedupe. Key capabilities: file-based history, title/URL/event matching, auto-trim (200 max), companion script news-track.py."
agent: general-purpose
---

# News Dedup Tracker

Persistent deduplication for news-pushing cron jobs. Uses a local JSON file to track already-pushed headlines, preventing the same story from being sent twice across repeated cron runs.

## Inputs

1. A cron job that fetches and pushes breaking news.
2. The `news-track.py` script at `~/.hermes/scripts/news-track.py`.

## Output

- A JSON history file at `~/.hermes/data/news_history.json` that grows to 200 entries then auto-trims oldest.
- Cron jobs that push only genuinely new stories, not repeats.

## Process

### 1. Install the companion script

Ensure `~/.hermes/scripts/news-track.py` exists (attached to this skill). It provides three commands:

```bash
# Check if a story was already pushed
python3 ~/.hermes/scripts/news-track.py check "Title" "https://url"

# Record newly pushed stories
python3 ~/.hermes/scripts/news-track.py record '[{"title":"标题","url":"https://..."}]'

# Show the last N history entries
python3 ~/.hermes/scripts/news-track.py list
```

Initialize the history file:
```bash
echo '[]' > ~/.hermes/data/news_history.json
```

### 2. Add dedup rules to the cron prompt

Replace any existing dedup section with:

```
== 去重规则（强制，基于文件记录）==
1. 先读取 ~/.hermes/data/news_history.json（JSON数组），逐条判断候选新闻是否已推送过。
2. 判重规则：标题相同、URL相同、或同一事件（主体+动作+客体一致）均判重复，跳过。
3. 确认要推送的新闻列表后，在输出之前先执行：
   python3 ~/.hermes/scripts/news-track.py record '[{"title":"标题1","url":"来源链接1"},{"title":"标题2","url":"来源链接2"}]'
4. 文件保留最多 200 条，超出自动裁剪。
5. 实时重大新闻从严：全重复则回复 exactly [SILENT]。
6. 全重复无新进展则 [SILENT]。
7. 首次或 history 为空时直接推送，不判重。
```

### 3. Verify dedup works

Run the cron job manually, then check:
```bash
python3 ~/.hermes/scripts/news-track.py list
```
Running it again within 15 min should not repeat the same stories.

### 4. Cron prompt tips

- Place dedup rules after search/retrieval rules, before output format section.
- If a cron run finds nothing new, reply `[SILENT]` — history file unchanged.
- The script handles JSON escaping automatically.
