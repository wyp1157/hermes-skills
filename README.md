# Hermes Skills 🧠

> Hermes Agent 可复用技能仓库 —— 让 AI Agent 更聪明、更强大

---

## 📦 技能一览

| 技能 | 路径 | 说明 |
|------|------|------|
| 🎯 QQ Bot 图题答题 | `skills/messaging/qq-bot-image-quiz/` | QQ机器人图题问答流程：发图 + InlineKeyboard按钮 + 回调轮询完整方案 |
| 🚦 知识验证门禁 | `skills/productivity/knowledge-gate-system/` | 前置知识验证门禁：全自动 QQ 按钮答题循环、错题跟踪、Cron 联动、成都/四川科目一地区过滤 |
| 📰 新闻去重追踪 | `skills/cron/news-dedup-tracker/` | 基于文件的新闻推送去重系统：历史记录、标题/URL/事件匹配、自动裁剪200条上限、配套 news-track.py 脚本 |

---

## 🚀 安装使用

### 一键安装技能

```bash
hermes skills install \
  https://raw.githubusercontent.com/wyp1157/hermes-skills/main/skills/messaging/qq-bot-image-quiz/SKILL.md \
  --name qq-bot-image-quiz

hermes skills install \
  https://raw.githubusercontent.com/wyp1157/hermes-skills/main/skills/productivity/knowledge-gate-system/SKILL.md \
  --name knowledge-gate-system

hermes skills install \
  https://raw.githubusercontent.com/wyp1157/hermes-skills/main/skills/cron/news-dedup-tracker/SKILL.md \
  --name news-dedup-tracker
```

安装后 Hermes Agent 自动加载该技能，在相关场景下会按技能指引工作。

### 克隆到本地

```bash
git clone https://github.com/wyp1157/hermes-skills.git
cd hermes-skills
```

---

## 🧩 技能详解

### QQ Bot 图题答题

**场景**：在 QQ 群/私聊中发送带图片的答题题目，用户点击按钮选择答案。

**核心流程**：
1. 先发题目图片（QQ 原生图片消息）
2. 紧跟 Markdown 文字 + InlineKeyboard 答题按钮
3. 通过网关回调获取用户选择
4. 支持单选/多选/判断题

**详细内容**：参见 `skills/messaging/qq-bot-image-quiz/SKILL.md`

### 知识验证门禁

**场景**：在执行新闻推送、日常任务或其他 Agent 能力前，要求用户先完成知识测验。

**核心流程**：
1. `status` 检查当天门禁状态
2. `quiz N timeout` 启动单进程全自动答题循环
3. QQ 按钮回调写入答案文件，脚本自动判题并推进下一题
4. 完成后写入 `completed`，错题进入错题本
5. 科目一默认过滤为全国题 + 四川成都题，避免混入外地地域题

**详细内容**：参见 `skills/productivity/knowledge-gate-system/SKILL.md`

### 新闻去重追踪

**场景**：Cron 定时推送重大新闻时，避免同一新闻重复推送。

**核心流程**：
1. 安装 news-track.py 脚本，初始化新闻历史 JSON 文件
2. 在 Cron prompt 中加入文件判重规则
3. 每轮推送前读取 history 文件 → 判重 → 推送 → 记录新条目
4. 自动裁剪历史记录到最近 200 条

**详细内容**：参见 `skills/cron/news-dedup-tracker/SKILL.md`

---

## 🤝 贡献

欢迎提 PR 提交你自己的 Hermes Agent 技能！

**规范要求**：
- 技能文件路径：`skills/<类别>/<技能名>/SKILL.md`
- 遵循 Hermes Agent SKILL.md 格式（YAML 元信息 + Markdown 正文）
- 包含清晰的场景触发条件、实现步骤、常见坑点

---

## 📜 许可证

MIT © [wyp1157](https://github.com/wyp1157)
