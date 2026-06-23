---
name: knowledge-gate-system
title: Knowledge Gate System
description: 构建前置知识验证门禁系统 — 在允许用户使用Agent之前，先通过答题/验证才能解锁。支持状态机管理、错题跟踪、Cron主动推送。
trigger: 用户要求"先答对题才能用我"或类似的前置验证门禁需求
---

# Knowledge Gate System (知识验证门禁)

## 适用场景

用户要求在使用Agent之前必须先通过某项验证：
- 驾考题库每日抽查（科目一/科目四）
- 外语单词每日考核
- 知识复习验证
- 任何"先答对再干活"的场景

## 架构总览

```
┌─────────────────────────────────────────────────┐
│                  Knowledge Gate                   │
├─────────────────────────────────────────────────┤
│  State Machine (Python)                          │
│    pending ──start──▶ in_progress ──done──▶ completed│
│                    ▲              │               │
│                    └── retry ─────┘               │
├─────────────────────────────────────────────────┤
│  Persistence: JSON files (~/.hermes/<topic>/)     │
│  Self-check: Memory entry (loaded each turn)      │
│  Proactive: Cron job at random daily intervals    │
└─────────────────────────────────────────────────┘
```

## 实现步骤

### 1. 数据准备

```bash
mkdir -p ~/.hermes/<topic>
# 下载或准备题库数据保存为 questions.json
```

先了解数据结构：
```python
import json
with open('questions.json') as f:
    data = json.load(f)
print(f"总量: {len(data)}")
# 探查字段、题目类型分布、章节分布
```

### 2. 构建状态机脚本

位置：`~/.hermes/scripts/<topic>-gate.py`

**必须支持的命令：**

| 命令 | 功能 |
|------|------|
| `status` | 查今日状态 — pending/in_progress/completed |
| `start [N]` | 开始今日测验(N题)，优先抽错题 |
| `answer <答案>` | 提交答案，验证 → 推进或完成 |
| `reset` | 手动重置 |
| `wrong` | 看错题本 |
| `bypass` | 返回PASS/BLOCK（cron前置检查） |

**关键代码片段：**

```python
# 状态持久化
STATE_FILE = os.path.expanduser("~/.hermes/<topic>/state.json")

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"today": str(date.today()), "status": "pending", ...}
    with open(STATE_FILE) as f:
        state = json.load(f)
    # 日切换自动重置
    if state.get("today") != str(date.today()):
        state = {"today": str(date.today()), "status": "pending", ...}
    return state

def check_answer(q, user_answer):
    # 忽略空格大小写
    return user.upper().replace(" ", "") == correct.upper().replace(" ", "")
```

### 2a. 题目配图/动画增强

题库中题目可能有以下媒体字段，需要在`format_question()`中输出：

```python
def get_question_media(q):
    """获取题目媒体资源"""
    parts = []
    img_url = q.get("url", "") or ""
    if img_url.strip():
        parts.append(f"📷 看图：{img_url.strip()}")
    cover = q.get("coverUrl", "") or ""
    if cover.strip() and cover.strip() != img_url.strip():
        parts.append(f"📷 附图：{cover.strip()}")
    vid = q.get("aliyVid", "") or ""
    if vid.strip() and q.get("vedioExplainFlag"):
        parts.append(f"🎬 本题有视频讲解")
    return "\n".join(parts)
```

配图URL以可点击的纯文本链接形式嵌入题目输出中。用户在QQ上点链接就能看图。

### 2b. 选项格式 — 按钮版（QQ Bot 推荐）

QQ Bot 支持 InlineKeyboard 按钮，有三种题型键盘：

**单选题：** 点击选项 → 直接提交答案（`quiz:N:LETTER`）
**判断题：** 点击「正确」或「错误」→ 直接提交
**多选题：** 点击选项切换 ⬜/✅ 状态 → 点「📋 提交答案」合并提交

按钮由 `driving-quiz.py` 的 `_build_*_keyboard` 函数构建，通过 QQ Bot REST API 直接发送。

**回退方案：** 如果发送失败，自动用 `[A] [B] [C] [D]` 文字格式，用户回一个字母即可。

对判断题：`[A] 正确 [B] 错误`
对多选题末尾加标注：`（多选，如 ABC）`

详见 `references/qq-bot-quiz-delivery.md`。

### 2c. 易错率等增强信息

如果题库有`errorRate`字段，高易错率的题自动标注：

```python
error_rate = q.get("errorRate", "")
err_tag = f" 易错率{error_rate}%" if error_rate and float(error_rate) > 20 else ""
```

### 3. 注册自检记忆

```markdown
【<Topic>答题门禁】每天必须先答完测试才能处理其他事务。
脚本在 ~/.hermes/scripts/<topic>-gate.py，状态文件 ~/.hermes/<topic>/state.json。
每次用户发消息：
1. 先 python3 ~/.hermes/scripts/<topic>-gate.py status 查状态
2. status=pending → 启动全自动测验（quiz N timeout）
3. status=in_progress → 等待全自动测验进程处理按钮回调
4. status=completed → 正常响应
```

### 4a. Cron与新闻推送联动

当门禁需要**在新闻推送前先弹出答题**时，在每个新闻cron的prompt头部加上前置检查：

```markdown
== 前置检查：科目一答题门禁 ==
先运行: python3 ~/.hermes/scripts/<topic>-gate.py status
如果返回"已完成" → 跳过门禁，正常执行新闻任务
如果返回"未答题" → 运行 python3 -u ~/.hermes/scripts/<topic>-gate.py quiz N 900，推题并等待按钮答题，然后 [SILENT]
如果返回"答题中" → 提醒"先答完题再看新闻"，然后 [SILENT]
```

注意：15分钟间隔的实时新闻cron，同小时内不应重复推送答题提醒（用计时或状态文件防刷）。

### 5. 设置Cron主动推送

```python
cronjob(action='create', name='<Topic>抽查', schedule='0 8,11,14,17,20 * * *',
    prompt='检查答题状态，未完成则运行全自动 quiz N 900', deliver='origin')
```

## 错误处理/Pitfalls

### ⚠️ 用户中断答题
- 用户发非答案内容时礼貌拒绝："先答完题再办事"
- 分多条消息的只取最后一条有效内容

### ⚠️ 日切换
- 状态文件date字段校验，日期变了自动重置为pending
- Cron在日切后第一次运行不应重复推送

### ⚠️ 错题复习
- 优先从错题本抽题（占50%），再补新题
- 连续答对同错题3次可考虑移除
- 连续答错3次以上降低出现频率

### ⚠️ 本地题库地域过滤
- `~/.hermes/driving-test/questions.json` 可能混入外地地域题（如济南 `regionCode=370100`）
- 科目一成都/四川默认抽题只保留全国题（`regionCode=0`/空）和四川成都题（`regionCode=510100`）
- 抽题逻辑必须先调用地域过滤，再随机抽题/错题复习，避免把外地城市法规题发给用户

### ⚠️ 按钮轮询必须后台运行（关键实践坑）
分步 `start + poll + answer + poll` 容易在第一题后断链：旧 `poll` 进程拿到一次答案就退出，若没有重新启动监听，下一题按钮虽然发出但不会被处理。

**推荐做法：** 把门禁入口统一切到单进程全自动循环：
```bash
cd ~/.hermes/scripts && python3 -u driving-quiz.py quiz 20 900
```
- `quiz N timeout` 在同一个进程里完成：发题 → 等按钮回调 → 判题/记错 → 自动进入下一题。
- cron/新闻门禁/抽查任务都应调用 `quiz 20 900`，不要再调用旧 `start 20`。
- `start` 可以作为兼容入口，但应内部转发到 `cmd_quiz()`。
- 保留 `poll` 仅用于调试或旧流程兼容；不要把它作为默认生产门禁链路。

**全自动循环模式：**
```
① cmd_quiz(N, timeout) → 创建会话 + 发Q1按钮
② 用户点按钮 → Gateway写 button_answer.json
③ 同一进程读取答案 → 判题/记错 → 发Q2按钮
④ 重复②-③直至完成或单题超时
```

### ⚠️ Cron不会锁Agent
- 门禁靠**记忆中的自检规则**强制执行
- 用户发/new可重置会话绕过 — 设计限制

### ⚠️ QQ Bot平台适配
- **图片**：只能发可点击URL链接（`📷 看图：http://...`），`MEDIA:`和CQ码在QQ上均不可用
- **InlineKeyboard按钮（推荐）**：通过 `_send_qq_c2c_message` 直接调用 QQ Bot REST API 发送按钮。按钮的 `data` 字段格式详见 `references/qq-bot-quiz-delivery.md`。Gateway 的 `adapter.py#1180-1256` 自动处理三种回调（answer/toggle/submit），写入 `button_answer.json` 供脚本轮询。
- **按钮发送失败自动回退**：`cmd_send()` 在 `_send_qq_c2c_message` 返回 False 时打印文字版 `[A] [B]` 格式作为 fallback。
- **轮询模式**：发送按钮后，Agent 用 `cmd_poll(timeout)` 循环检查 `button_answer.json`（每1.5秒），直到用户点击或超时。`cmd_start()` 和 `cmd_answer()` 都内置了自动 `cmd_send()` 接续。
- **长消息**：QQ对超长消息有截断风险，多题分多条消息发送
- **答案格式**：如 "A,B,C"，比较时忽略空格大小写；接受 "ABC" 或 "A,B,C" 两种输入格式
- 详见 `references/qq-bot-quiz-delivery.md`

## 验证检查

```bash
# 查状态
python3 ~/.hermes/scripts/<topic>-gate.py status

# 开始测验
python3 ~/.hermes/scripts/<topic>-gate.py start 3

# 提交答案
python3 ~/.hermes/scripts/<topic>-gate.py answer A

# 查看错题
python3 ~/.hermes/scripts/<topic>-gate.py wrong

# 绕过检查
python3 ~/.hermes/scripts/<topic>-gate.py bypass

# 重置
python3 ~/.hermes/scripts/<topic>-gate.py reset
```

## 参考

参考实现：`~/.hermes/scripts/driving-quiz.py`（科目一答题门禁完整实现）
参考文档：`skill_view(name='knowledge-gate-system', file_path='references/driving-quiz-implementation.md')` — 具体数据源、状态文件格式、题目格式化方式
参考文档：`skill_view(name='knowledge-gate-system', file_path='references/qq-bot-quiz-delivery.md')` — QQ Bot平台图片投递、按钮替代方案、新闻联动模式
参考文档：`skill_view(name='knowledge-gate-system', file_path='references/auto-quiz-loop.md')` — 全自动按钮测验循环、第一题后断链修复、隔离验证模板
