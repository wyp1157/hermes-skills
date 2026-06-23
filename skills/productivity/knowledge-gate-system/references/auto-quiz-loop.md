# 全自动按钮测验循环模式

## 适用场景

用于 QQ Bot / InlineKeyboard / 知识门禁类测验：用户点按钮提交答案，网关把结果写入 `button_answer.json`，脚本负责判题和推进状态。

## 反模式

不要把生产链路做成：

```bash
start -> poll -> answer -> poll -> answer ...
```

原因：`poll` 通常拿到一次答案就退出。若 Agent 没有重新启动下一轮 `poll`，就会出现“第一题答完后没有后续”的断链。

## 推荐结构

统一提供一个全自动入口：

```bash
python3 -u driving-quiz.py quiz 20 900
```

`quiz` 在同一进程内完成：

1. 初始化/重置当天测验状态。
2. 发送当前题按钮。
3. 循环读取 `button_answer.json`，等待当前题答案。
4. 校验 `question_index == current_index + 1`，丢弃过期按钮结果。
5. 判题、计分、记录错题。
6. 推进 `current_index` 并发送下一题。
7. 全部完成后写入 `status=completed`。

## 实现要点

- `start` 可以保留为兼容入口，但应内部转发到 `cmd_quiz()`。
- `answer` 可以保留为调试入口，但不要让生产 cron 依赖它。
- `poll` 只用于故障排查或旧流程兼容，不作为默认门禁链路。
- cron / 新闻前置门禁 / 随机抽查都应调用 `quiz 20 900`，不要调用 `start 20`。
- 运行 `quiz` 的 cron 或后台进程需要足够长的超时，至少覆盖 `题数 × 单题等待时间`。

## 隔离验证模板

验证时不要污染正式 `~/.hermes/driving-test`。使用临时 `HOME`，写入 2 道测试题，stub 掉 QQ 发送函数，并用后台线程模拟两次按钮回调。

成功信号：

```text
[Q1] 收到答案：A
[Q2] 收到答案：B
🎉 答题完成
FINAL_STATE completed 2 2 2
```

## 故障定位

| 现象 | 常见原因 | 处理 |
|---|---|---|
| 第一题后无后续 | 仍在走 `start + poll + answer` 半自动链路 | 把入口换成 `quiz` |
| 用户点了但脚本忽略 | `question_index` 与当前题不匹配 | 检查状态文件和旧 `button_answer.json` |
| cron 触发后卡住 | 前台跑长轮询且任务超时不足 | 用 `python3 -u ... quiz N timeout` 并调大任务超时 |
| 下一题发了但没处理 | 旧 poll 已退出 | 不要依赖 poll，改全自动循环 |
