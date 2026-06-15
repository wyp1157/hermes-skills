# Hermes Skills 🧠

> Hermes Agent 可复用技能仓库 —— 让 AI Agent 更聪明、更强大

---

## 📦 技能一览

| 技能 | 路径 | 说明 |
|------|------|------|
| 🎯 QQ Bot 图题答题 | `skills/messaging/qq-bot-image-quiz/` | QQ机器人图题问答流程：发图 + InlineKeyboard按钮 + 回调轮询完整方案 |

---

## 🚀 安装使用

### 一键安装技能

```bash
hermes skills install \
  https://raw.githubusercontent.com/wyp1157/hermes-skills/main/skills/messaging/qq-bot-image-quiz/SKILL.md \
  --name qq-bot-image-quiz
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
3. 通过网关回调轮询获取用户选择
4. 支持单选/多选/判断题

**详细内容**：参见 `skills/messaging/qq-bot-image-quiz/SKILL.md`

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
