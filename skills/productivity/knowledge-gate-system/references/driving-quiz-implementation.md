# 科目一答题门禁 — 参考实现

本参考文档记录了科目一答题门禁系统的完整实现细节，作为 knowledge-gate-system 技能的具体实例。

## 数据来源

**题库**: [doupoa/DrivingTestSubjectOne](https://github.com/doupoa/DrivingTestSubjectOne) (MIT开源)
- 题量: **4,378题**（原始题库，含全国题和部分地方题）
- 默认有效题池: **全国通用题 + 四川成都题**，抽题前按 `regionCode` 过滤
- 地区过滤: 保留 `regionCode=0` / 空值 / `510100`，排除济南 `370100` 等外地地域题
- 章节: 15章（交通信号1242题、安全驾驶547题、处罚184题等）
- 题目类型: 单选题(1854)、多选题(279)、判断题(2245)
- 字段: question, itemsDescArray(选项文本), itemsTitleArray(选项字母), answer, answerSkillExplain(解析), difficulty(难度1-5), chapterId(章节), regionCode(地区码)

```bash
# 下载方式
curl -L -o ~/.hermes/driving-test/questions.json \
  "https://raw.githubusercontent.com/doupoa/DrivingTestSubjectOne/master/%E9%A2%98%E5%BA%93JSON/Subject1.json"
```

## 文件结构

```
~/.hermes/driving-test/
├── questions.json              # 题库 (5.97MB, 4378题)
├── quiz_state.json             # 今日答题状态
├── wrong_questions.json        # 错题本
└── wrong_questions.txt         # 错题本纯文本导出

~/.hermes/scripts/
└── driving-quiz.py             # 答题引擎
```

## 持久化文件

| 文件 | 作用 | 生命周期 |
|------|------|---------|
| `quiz_state.json` | 当日答题状态 | 逐日重置 |
| `correct_questions.json` | 已答对题目ID列表 | 整个循环（全部刷完重置） |
| `wrong_questions.json` | 错题本（含错误次数） | 答对后自动移除 |

## 答题去重策略

**核心规则：正确的题目在当前循环内不重复出现。**

- 选题时：排除 `correct_questions.json` 中的题 + 排除 `wrong_questions.json` 中的题 → 抽新鲜题
- 错题优先：从错题池中抽最多一半，确保错题反复出现直到答对
- 答对立即移除：答对后同时从 `wrong_questions.json` 移除该题 → 后续不再抽到
- 循环重置：当 `correct_questions.json` 覆盖全部题库时，清空正确记录，新一轮循环开始

## 状态文件格式 (quiz_state.json)

```json
{
  "today": "2026-06-15",
  "status": "pending|in_progress|completed",
  "questions": [],
  "current_index": 0,
  "correct_count": 0,
  "total_asked": 0
}
```

## 题目格式化

三种题型格式化方式：

```
# 判断题 (type=3)
【第1题】【判断题】驾驶机动车...（⭐⭐）
A. 正确
B. 错误

# 单选题 (type=1)
【第2题】【单选题】如图所示...（⭐⭐⭐）
A. 减速通过
B. 停车察明水情
C. 快速通过
D. 可随意通行

# 多选题 (type=2)
【第3题】【多选题】陶某驾驶...（⭐⭐⭐⭐）
A. 陶某客车超员
B. 陶某超速行驶
C. 安某未按规定设置警示标志
D. 安某违法停车
（可多选，如 ABC）
```

## QQ Bot 按钮集成要点

### Token 获取（⛔ 易错点）

```python
# ❌ 错误 — HTTP 404
url = "https://api.sgroup.qq.com/v2/apps/%s/token" % QQ_APP_ID
data = {"app_id": QQ_APP_ID, "client_secret": QQ_CLIENT_SECRET}

# ✅ 正确
url = "https://bots.qq.com/app/getAppAccessToken"
data = {"appId": QQ_APP_ID, "clientSecret": QQ_CLIENT_SECRET}
```

旧版 endpoint `api.sgroup.qq.com/v2/apps/{id}/token` 已废弃但返回 **404**（不重定向），字段名也要从下划线式改成驼峰式。这个错不会给出明确提示——Token 获取失败后后续 API 调用静默失败。

### 按钮发送关键组合

- `msg_type: 2` + `markdown` 字段 = 按钮能显示
- `msg_type: 0` + `content` + keyboard = HTTP 200 但按钮不显示
- Authorization: `QQBot {token}`（不是 `Bearer`）

### 三种键盘类型

| 题型 | 构建函数 | 回调 data 格式 | 按钮行为 |
|------|---------|---------------|---------|
| 判断题 | `_build_judge_keyboard(idx)` | `quiz:{N}:A` / `quiz:{N}:B` | 点击即提交 |
| 单选题 | `_build_single_choice_keyboard(idx, titles, items)` | `quiz:{N}:{LETTER}` | 点击即提交 |
| 多选题 | `_build_multi_choice_keyboard(idx, titles, items)` | `quiz:toggle_{N}:{LETTER}` / `quiz:submit_{N}` | 切换→提交 |

### 回调处理流程

Gateway 的 `adapter.py#1180-1256` 处理 `INTERACTION_CREATE` 事件：
- `quiz:{N}:{LETTER}` → 单选/判断直接写入 `~/.hermes/scripts/driving-quiz/button_answer.json`
- `quiz:toggle_{N}:{LETTER}` → 维护 `multi_select_N.json` 切换状态
- `quiz:submit_{N}` → 合并已选项写入 `button_answer.json`

生产入口统一使用单进程全自动循环：

```bash
cd ~/.hermes/scripts && python3 -u driving-quiz.py quiz 20 900
```

`cmd_quiz()` 在同一进程里完成发题、等待按钮回调、判题、记录错题、自动进入下一题。旧 `cmd_poll(timeout)` 只保留为调试/兼容入口，不再作为生产门禁默认链路。

### 地域过滤流程

`questions.json` 原始题库可能混入地方题。成都/四川科目一默认抽题前必须先过滤：

```python
questions = filter_questions_for_region(load_questions())
```

过滤规则：
- 保留全国题：`regionCode in ("", "0")`
- 保留四川成都题：`regionCode == "510100"`
- 排除其他地区题：如济南 `370100`

## Cron配置

```
计划: 0 8,11,14,17,20 * * *
每天5个时段推送, 已答题则静默跳过
```

新闻 cron 的 prompt 头部前置检查：
```markdown
== 前置检查：科目一答题门禁 ==
先运行: python3 ~/.hermes/scripts/driving-quiz.py status
如果返回"已完成" → 跳过门禁，正常执行新闻任务
如果返回"未答题" → 运行 python3 -u ~/.hermes/scripts/driving-quiz.py quiz 20 900，然后 [SILENT]
如果返回"答题中" → 提醒"先答完题再看新闻"，然后 [SILENT]
```

## 自检记忆

已保存至 memory, 每次用户发消息时自动加载:
- status=pending → 自动运行 `quiz 20 900` 全自动出题
- status=in_progress → 等待当前全自动 quiz 进程处理按钮答案
- status=completed → 正常处理
