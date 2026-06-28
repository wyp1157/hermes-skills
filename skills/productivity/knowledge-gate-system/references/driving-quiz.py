#!/usr/bin/env python3
"""
科目一驾考题库引擎 (Button Edition)
用法:
  python3 driving-quiz.py status                    -> 查看今日答题状态
  python3 driving-quiz.py quiz [N] [timeout]        -> 全自动测验(N题,默认20)
  python3 driving-quiz.py start [N]                 -> 兼容入口，内部转发到 quiz
  python3 driving-quiz.py answer <答案>              -> 调试入口，不作为生产链路
  python3 driving-quiz.py reset                      -> 手动重置今日状态(管理员用)
  python3 driving-quiz.py wrong                      -> 查看错题本
  python3 driving-quiz.py bypass                     -> BYPASS(仅限cron前置检查用)
  python3 driving-quiz.py send                       -> 发送当前题目(含QQ Bot按钮)
  python3 driving-quiz.py check-button               -> 检查是否有按钮答题结果
"""
import json, sys, os, random, time, base64, urllib.request, urllib.error, pathlib
from datetime import date, datetime

# ===== 加载 .env 文件（先加载，这样后续 os.environ.get 能读到）=====
_env_path = pathlib.Path(os.path.expanduser("~/.hermes/.env"))
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip().strip("\"'")
                if _k not in os.environ:  # 已有的环境变量优先级更高
                    os.environ[_k] = _v

BASE = os.path.expanduser("~/.hermes/driving-test")
QUESTIONS_FILE = os.path.join(BASE, "questions.json")
STATE_FILE = os.path.join(BASE, "quiz_state.json")
WRONG_FILE = os.path.join(BASE, "wrong_questions.json")
CORRECT_FILE = os.path.join(BASE, "correct_questions.json")
BUTTON_ANSWER_FILE = os.path.expanduser("~/.hermes/scripts/driving-quiz/button_answer.json")
DEFAULT_QUIZ_COUNT = 20

# ===== QQ Bot API helpers =====
QQ_APP_ID = os.environ.get("QQ_APP_ID", "1903407760")
QQ_CLIENT_SECRET = os.environ.get("QQ_CLIENT_SECRET", "")
# DM C2C 用户的 openid (固定，因为只有牛哥一个人用)
QQ_USER_OPENID = "E9BC8AA42AA1278410F5FF248D766B22"


def _get_qq_token():
    """Get QQ Bot access token using app_id + client_secret."""
    url = "https://bots.qq.com/app/getAppAccessToken"
    data = json.dumps({
        "appId": QQ_APP_ID,
        "clientSecret": QQ_CLIENT_SECRET,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            return result.get("access_token", "")
    except Exception as e:
        print("[QQ Token Error] %s" % e, file=sys.stderr)
        return ""


def _send_qq_c2c_message(text, keyboard=None, file_info=None):
    """Send a C2C message with optional inline keyboard and embedded image.

    Args:
        text: Markdown text
        keyboard: Optional inline keyboard dict
        file_info: Optional file_info for embedded image
    """
    token = _get_qq_token()
    if not token:
        print("[QQ Send Error] No token", file=sys.stderr)
        return False

    url = "https://api.sgroup.qq.com/v2/users/%s/messages" % QQ_USER_OPENID
    body = {
        "content": text,
    }

    if file_info:
        # msg_type: 7 = Markdown + media（图片嵌入文本中）
        body["msg_type"] = 7
        body["markdown"] = {"content": text}
        body["media"] = {"file_info": file_info}
    else:
        body["msg_type"] = 2  # Markdown only
        body["markdown"] = {"content": text}

    if keyboard:
        body["keyboard"] = keyboard

    req = urllib.request.Request(url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "QQBot %s" % token,
        })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("id", "") != ""
    except Exception as e:
        print("[QQ Send Error] %s" % e, file=sys.stderr)
        return False


def _build_single_choice_keyboard(question_index, titles, items=None):
    """Build inline keyboard JSON for single-choice question."""
    rows = []
    for i in range(0, len(titles), 2):
        buttons = []
        for letter in titles[i:i+2]:
            label = letter
            if items and letter in titles:
                idx = titles.index(letter)
                desc = items[idx][:10] if idx < len(items) else ""
                label = "%s %s" % (letter, desc)
            data = "quiz:%d:%s" % (question_index + 1, letter)
            buttons.append({
                "id": "q_%d_%s" % (question_index, letter),
                "render_data": {
                    "label": label,
                    "visited_label": "✓ %s" % letter,
                    "style": 1,
                },
                "action": {
                    "type": 1,  # Callback
                    "data": data,
                    "unsupport_tips": "请回复答案字母",
                    "permission": {"type": 2},  # 全员可点
                },
            })
        rows.append({"buttons": buttons})
    return {"content": {"rows": rows}}


def _build_multi_choice_keyboard(question_index, titles, items=None):
    """Build inline keyboard JSON for multi-choice question."""
    rows = []
    for i in range(0, len(titles), 2):
        buttons = []
        for letter in titles[i:i+2]:
            label = "⬜ %s" % letter
            if items and letter in titles:
                idx = titles.index(letter)
                desc = items[idx][:8] if idx < len(items) else ""
                label = "⬜ %s %s" % (letter, desc)
            data = "quiz:toggle_%d:%s" % (question_index + 1, letter)
            buttons.append({
                "id": "q_%d_%s" % (question_index, letter),
                "render_data": {
                    "label": label,
                    "visited_label": "✅ %s" % letter,
                    "style": 1,
                },
                "action": {
                    "type": 1,
                    "data": data,
                    "unsupport_tips": "请回复答案字母",
                    "permission": {"type": 2},
                },
            })
        rows.append({"buttons": buttons})

    # Submit button
    submit_data = "quiz:submit_%d" % (question_index + 1)
    rows.append({"buttons": [{
        "id": "submit_%d" % question_index,
        "render_data": {
            "label": "📋 提交答案",
            "visited_label": "已提交",
            "style": 1,
        },
        "action": {
            "type": 1,
            "data": submit_data,
            "unsupport_tips": "请回复字母组合答案",
            "permission": {"type": 2},
        },
    }]})
    return {"content": {"rows": rows}}


def _build_judge_keyboard(question_index):
    """Build keyboard for judge (true/false) question."""
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "q_%d_A" % question_index,
                            "render_data": {"label": "A. 正确", "visited_label": "✓ A. 正确", "style": 1},
                            "action": {"type": 1, "data": "quiz:%d:A" % (question_index + 1), "unsupport_tips": "请回复A或B", "permission": {"type": 2}},
                        },
                        {
                            "id": "q_%d_B" % question_index,
                            "render_data": {"label": "B. 错误", "visited_label": "✓ B. 错误", "style": 1},
                            "action": {"type": 1, "data": "quiz:%d:B" % (question_index + 1), "unsupport_tips": "请回复A或B", "permission": {"type": 2}},
                        },
                    ]
                }
            ]
        }
    }

# ===== 图片上传 =====
def _download_and_upload_image(image_url, srv_send_msg=False):
    """下载驾考题库图片并上传到QQ Bot，返回file_info用于嵌入消息。

    Args:
        image_url: 图片URL
        srv_send_msg: True=上传后QQ Bot自动把图发到对话框
    """
    token = _get_qq_token()
    if not token:
        return None

    # 1. 下载图片
    try:
        req = urllib.request.Request(image_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; HermesBot/1.0)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            image_data = resp.read()
    except Exception as e:
        print("[Image Download Error] %s" % e, file=sys.stderr)
        return None

    # 太大就不传了（QQ Bot上限约25MB，驾考题图很小）
    if len(image_data) > 25 * 1024 * 1024:
        print("[Image Too Large] %d bytes" % len(image_data), file=sys.stderr)
        return None

    # 2. 上传到QQ Bot file API
    b64 = base64.b64encode(image_data).decode()
    body = {
        "file_type": 1,  # MEDIA_TYPE_IMAGE
        "file_data": b64,
        "srv_send_msg": srv_send_msg,
    }
    url = "https://api.sgroup.qq.com/v2/users/%s/files" % QQ_USER_OPENID
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "QQBot %s" % token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            file_info = result.get("file_info", "")
            if file_info:
                print("[Upload OK] file_info=%s..." % file_info[:30])
            return file_info
    except Exception as e:
        print("[Image Upload Error] %s" % e, file=sys.stderr)
        return None


def _send_question_image_to_qq(image_url):
    """上传驾考题图片到QQ Bot并自动发送（独立图片消息），返回是否成功"""
    file_info = _download_and_upload_image(image_url, srv_send_msg=True)
    if not file_info:
        print("[Image] 发图失败", file=sys.stderr)
        return False
    # srv_send_msg=True时，上传API会自动把图发到用户的对话框
    print("[Image] ✅ 图片已发到QQ")
    return True


# ===== 题库加载 =====
def load_questions():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_questions_for_region(questions):
    """默认只保留全国题和四川题，避免混入外地地域题。"""
    allowed_regions = {"", "0", "510100"}
    filtered = [q for q in questions if str(q.get("regionCode", "")) in allowed_regions]
    if filtered:
        return filtered
    return questions
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"today": str(date.today()), "status": "pending", "questions": [], "current_index": 0, "correct_count": 0, "total_asked": 0}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    # 如果日期变了，重置
    if state.get("today") != str(date.today()):
        state = {"today": str(date.today()), "status": "pending", "questions": [], "current_index": 0, "correct_count": 0, "total_asked": 0}
    return state

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def load_wrong():
    if not os.path.exists(WRONG_FILE):
        return []
    with open(WRONG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_wrong(wrong):
    with open(WRONG_FILE, "w", encoding="utf-8") as f:
        json.dump(wrong, f, ensure_ascii=False, indent=2)

def load_correct():
    if not os.path.exists(CORRECT_FILE):
        return []
    with open(CORRECT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_correct(correct):
    with open(CORRECT_FILE, "w", encoding="utf-8") as f:
        json.dump(correct, f, ensure_ascii=False, indent=2)

# ===== 格式化题目 =====
def get_question_media(q):
    """获取题目的媒体资源（图片URL和视频）"""
    parts = []
    
    # 图片URL
    img_url = q.get("url", "") or ""
    if img_url.strip():
        parts.append(f"📷 看图：{img_url.strip()}")
    
    # coverUrl备用图
    cover = q.get("coverUrl", "") or ""
    if cover.strip() and cover.strip() != img_url.strip():
        parts.append(f"📷 附图：{cover.strip()}")
    
    # 视频
    vid = q.get("aliyVid", "") or ""
    if vid.strip() and q.get("vedioExplainFlag"):
        parts.append(f"🎬 本题有视频讲解")
    
    return "\n".join(parts)


def format_question(q, index=None, file_info=None):
    """将题目格式化为可读文本（含配图链接）

    Args:
        q: 题目数据
        index: 题号索引（从0开始）
        file_info: QQ Bot上传后的file_info，有则嵌入图片
    """
    qtype = q.get("type", 1)
    question = q["question"]
    items = q.get("itemsDescArray", [])
    titles = q.get("itemsTitleArray", [])
    diff_stars = "⭐" * q.get("difficulty", 1)

    prefix = f"**第{index+1}题**" if index is not None else ""

    # 题目标签
    tag = {3: "判断题", 2: "多选题", 1: "单选题"}.get(qtype, "题目")
    error_rate = q.get("errorRate", "")
    err_tag = f" 易错率{error_rate}%" if error_rate and float(error_rate) > 20 else ""

    # 先放图片（如果有）
    lines = []
    if file_info:
        lines.append(f"![image](file://{file_info})")
        lines.append("")

    lines.append(f"{prefix} **【{tag}】** {question}（{diff_stars}{err_tag}）")

    if qtype == 3:
        lines.append("")
        lines.append("[A] 正确")
        lines.append("[B] 错误")
    else:
        for t, d in zip(titles, items):
            lines.append(f"[{t}] {d}")
        if qtype == 2:
            lines.append("")
            lines.append("（多选，如 ABC）")

    # 没有嵌入图片时才放URL文本
    if not file_info:
        media = get_question_media(q)
        if media:
            lines.append("")
            lines.append(media)

    text = "\n".join(lines)
    return text.strip()

def get_answer_text(q):
    """返回正确答案的文本描述"""
    answer = q["answer"]
    items = q.get("itemsDescArray", [])
    titles = q.get("itemsTitleArray", [])
    
    if q.get("type") == 3:
        # 判断题
        idx = ["A", "B"].index(answer) if answer in ["A", "B"] else -1
        answer_text = items[idx] if idx >= 0 else answer
    elif q.get("type") == 2:
        # 多选题
        selected = [t for t in titles if t in answer.split(",")]
        descs = []
        for a in answer.split(","):
            a = a.strip()
            if a in titles:
                idx = titles.index(a)
                descs.append(items[idx] if idx < len(items) else a)
            else:
                descs.append(a)
        answer_text = ", ".join(descs)
    else:
        idx = titles.index(answer) if answer in titles else -1
        answer_text = items[idx] if idx >= 0 else answer
    
    return answer_text

def check_answer(q, user_answer):
    """检查答案是否正确"""
    correct = q["answer"].upper().replace(" ", "")
    user = user_answer.upper().replace(" ", "").strip()
    return user == correct

# ===== 主逻辑 =====
def cmd_status():
    state = load_state()
    today = str(date.today())
    same_day = state["today"] == today
    
    correct_total = len(load_correct())
    questions_all = filter_questions_for_region(load_questions())
    total_bank = len(questions_all)
    progress = f" | 累计已刷{correct_total}/{total_bank}题"
    
    if not same_day or state["status"] == "pending":
        print(f"今日({today})：❌ 未答题{progress}")
        return
    elif state["status"] == "in_progress":
        print(f"今日({today})：🔄 答题中（{state['correct_count']}/{state['total_asked']}正确，共{len(state['questions'])}题）{progress}")
        return
    elif state["status"] == "completed":
        rate = state["correct_count"] / state["total_asked"] * 100 if state["total_asked"] > 0 else 0
        print(f"今日({today})：✅ 已完成（{state['correct_count']}/{state['total_asked']}正确，正确率{rate:.0f}%）{progress}")
        return

def cmd_start(n=DEFAULT_QUIZ_COUNT):
    print("ℹ️ 已切换为全自动 quiz 模式，请直接运行 /quiz")
    return cmd_quiz(total_questions=n, poll_timeout=600)

def cmd_answer(user_ans):
    state = load_state()
    
    if state["status"] != "in_progress":
        print("❌ 还没有进行中的答题，先 /quiz start 开始")
        return
    
    idx = state["current_index"]
    if idx >= len(state["questions"]):
        print("❌ 所有题都答完了，但状态异常。试试 /quiz reset")
        return
    
    q = state["questions"][idx]
    correct = check_answer(q, user_ans)
    answer_text = get_answer_text(q)
    
    if correct:
        state["correct_count"] += 1
        state["total_asked"] += 1
        # 记录已答对题
        correct_list = load_correct()
        if q["id"] not in correct_list:
            correct_list.append(q["id"])
            save_correct(correct_list)
        # ✅ 从错题本移除（答对的题不再在当前循环出现）
        wrong = load_wrong()
        before = len(wrong)
        wrong = [w for w in wrong if w["id"] != q["id"]]
        if len(wrong) != before:
            save_wrong(wrong)
        print(f"✅ 正确！{answer_text}")
        print(f"💡 {q.get('answerSkillExplain', '')}")
    else:
        state["total_asked"] += 1
        # 记错题
        wrong = load_wrong()
        # 如果已在错题本，更新次数
        found = False
        for w in wrong:
            if w["id"] == q["id"]:
                w["count"] = w.get("count", 0) + 1
                w["last_wrong"] = str(datetime.now())
                found = True
                break
        if not found:
            wrong.append({
                "id": q["id"],
                "question": q["question"],
                "answer": q["answer"],
                "answer_text": answer_text,
                "explain": q.get("answerSkillExplain", ""),
                "count": 1,
                "last_wrong": str(datetime.now())
            })
        save_wrong(wrong)
        print(f"❌ 错误！正确答案：{answer_text}")
        print(f"💡 {q.get('answerSkillExplain', q.get('remark', ''))}")
    
    # 下一题或完成
    idx += 1
    if idx >= len(state["questions"]):
        state["status"] = "completed"
        state["current_index"] = idx
        save_state(state)
        rate = state["correct_count"] / state["total_asked"] * 100 if state["total_asked"] > 0 else 0
        wrong_count = state["total_asked"] - state["correct_count"]
        correct_total = len(load_correct())
        questions_all = filter_questions_for_region(load_questions())
        total_bank = len(questions_all)
        remaining = total_bank - correct_total
        print("---")
        print(f"🎉 答题完成！{state['correct_count']}/{state['total_asked']}正确（正确率{rate:.0f}%），错了{wrong_count}题已自动记入错题本")
        print(f"错题总数：{len(load_wrong())}题 — 每道错题都会在后续抽考中反复出现直到记住！")
        print(f"已累计答对{correct_total}/{total_bank}题")
        print("✅ 今日门禁已开，可以自由使用了！")
        # 发QQ通知
        summary = f"🎉 答题完成！{state['correct_count']}/{state['total_asked']}正确（正确率{rate:.0f}%）\n📚 错题{len(load_wrong())}道 | 已刷{correct_total}/{total_bank}题"
        if remaining <= 0:
            summary += "\n🏁 恭喜全部题库刷完一遍！"
        _send_qq_c2c_message(summary)
        return
    
    state["current_index"] = idx
    save_state(state)
    
    next_q = state["questions"][idx]
    # 如果答错了，多问一题补偿
    if not correct and state["total_asked"] - state["correct_count"] >= 1:
        # 不额外抽了，直接下一题
        pass
    
    print("---")
    print(format_question(next_q, idx))
    # 兼容旧 answer 命令：仍自动发送下一题；正式门禁已切到 quiz 全自动循环。
    cmd_send()

def cmd_reset():
    state = load_state()
    state["status"] = "pending"
    state["questions"] = []
    state["current_index"] = 0
    state["correct_count"] = 0
    state["total_asked"] = 0
    save_state(state)
    # 正确记录保留不清（只清当日答题状态）
    print("✅ 今日答题状态已重置（正确记录保留）")
    
    # 如需同时清正确记录：python3 driving-quiz.py reset all

def cmd_reset_all():
    """完全重置：清今日答题状态 + 正确记录 + 错题本"""
    cmd_reset()
    save_correct([])
    save_wrong([])
    print("✅ 已清除全部记录（正确记录+错题本已清空）")

def cmd_wrong():
    wrong = load_wrong()
    if not wrong:
        print("✅ 错题本为空，继续保持！")
        return
    # 按错误次数排序
    wrong.sort(key=lambda x: x.get("count", 0), reverse=True)
    print(f"📚 错题本（共{len(wrong)}题）：")
    for i, w in enumerate(wrong[:10]):
        print(f"\n{i+1}. {w['question']}")
        print(f"   正确答案：{w.get('answer_text', w['answer'])}")
        print(f"   错了{w.get('count', 1)}次 | {w.get('explain', '')[:80]}")
    if len(wrong) > 10:
        print(f"\n...还有{len(wrong)-10}题，/quiz wrong 查看全部")
    
    # 保存格式化的纯文本版到文件
    with open(os.path.join(BASE, "wrong_questions.txt"), "w", encoding="utf-8") as f:
        for i, w in enumerate(wrong):
            f.write(f"{i+1}. {w['question']}\n")
            f.write(f"   答案：{w.get('answer_text', w['answer'])}\n")
            f.write(f"   解析：{w.get('explain', '')}\n")
            f.write(f"   错误次数：{w.get('count', 1)}\n\n")
    print(f"📄 已导出到 wrong_questions.txt")

def cmd_correct():
    """查看已答对题目进度"""
    correct = load_correct()
    questions = filter_questions_for_region(load_questions())
    total = len(questions)
    done = len(correct)
    pct = done / total * 100 if total > 0 else 0
    print(f"📊 已累计答对：{done}/{total}题（{pct:.1f}%）")
    remaining = total - done
    if remaining <= 0:
        print("🏁 恭喜！全部题库已刷完一遍。继续刷题将启用新的随机循环！")

def cmd_bypass():
    """用于cron前置检查：如果今天答完了返回true"""
    state = load_state()
    today = str(date.today())
    if state["today"] == today and state["status"] == "completed":
        print("PASS")
        return True
    else:
        print("BLOCK")
        return False


def cmd_send():
    """发送当前题目到QQ (含按钮键盘，有图则嵌入图片)"""
    state = load_state()
    if state["status"] != "in_progress":
        print("❌ 没有进行中的答题")
        return

    idx = state["current_index"]
    if idx >= len(state["questions"]):
        print("❌ 所有题已答完，状态异常")
        return

    q = state["questions"][idx]
    qtype = q.get("type", 1)
    titles = q.get("itemsTitleArray", [])
    items = q.get("itemsDescArray", [])

    # 检查是否有图片URL，有则先发图
    img_url = (q.get("url", "") or "").strip()
    if img_url:
        print("[Image] 检测到配图，开始上传并发送图片…")
        _send_question_image_to_qq(img_url)

    # 格式化题目文本（不嵌图，因为图已单独发送）
    img_sent = bool(img_url)
    text = format_question(q, idx, file_info=None)

    # 构建键盘
    if qtype == 3:
        keyboard = _build_judge_keyboard(idx)
    elif qtype == 2:
        keyboard = _build_multi_choice_keyboard(idx, titles, items)
    else:
        keyboard = _build_single_choice_keyboard(idx, titles, items)

    success = _send_qq_c2c_message(text, keyboard)
    if success:
        print("✅ 题目已发送（含按钮%s）" % ("+图片" if img_sent else ""))
    else:
        print("⚠️ 题目发送失败（将使用文字模式）")
        print("---")
        print(text)


def cmd_check_button():
    """检查是否有按钮答题结果"""
    if not os.path.exists(BUTTON_ANSWER_FILE):
        print("NO_ANSWER")
        return None

    try:
        with open(BUTTON_ANSWER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        question_index = data.get("question_index", 0)
        answer = data.get("answer", "")
        mode = data.get("mode", "answer")
        
        state = load_state()
        # 验证question_index是否匹配当前题目
        if state["status"] != "in_progress":
            # 过期数据，清除
            os.remove(BUTTON_ANSWER_FILE)
            print("NO_ANSWER")
            return None
        
        idx = state["current_index"]
        if question_index != idx + 1:
            # question_index不匹配(可能是旧答题的残留)
            os.remove(BUTTON_ANSWER_FILE)
            print("NO_ANSWER")
            return None
        
        # 有效答案，输出答案格式供 cmd_answer 处理
        print("ANSWER:%s" % answer)
        # 清除按钮回答文件
        os.remove(BUTTON_ANSWER_FILE)
        return answer
    except Exception as e:
        print("ERROR:%s" % e, file=sys.stderr)
        return None

def cmd_poll(timeout=600):
    '''轮询按钮答案，直到用户点击按钮或超时。
    timeout: 最大等待秒数（默认600秒=10分钟）
    返回答案字母，超时返回None。
    '''
    import time as _time
    deadline = _time.time() + timeout
    check_interval = 1.5  # 1.5秒查一次
    
    while _time.time() < deadline:
        try:
            result = _check_button_answer_file()
            if result is not None:
                print(result)
                return result
        except Exception:
            pass
        _time.sleep(check_interval)
    
    print("TIMEOUT")
    return None


def cmd_quiz(total_questions=DEFAULT_QUIZ_COUNT, poll_timeout=600):
    """全自动答题循环：一次调用完成全部答题流程。
    
    流程：
      1. 启动今日测验（state -> in_progress）
      2. 循环每题：发题(含图片+按钮) -> 轮询等用户按钮答案 -> 处理答案(自动记错) -> 下一题
      3. 全部答完后输出结果
    
    本命令在后台运行时，我（AI）不需要任何手动介入。
    """
    import time as _time
    
    # ===== 1. 启动测验 =====
    questions = filter_questions_for_region(load_questions())
    state = load_state()
    today = str(date.today())
    
    # 如果今天已完成，不重复
    if state["today"] == today and state["status"] == "completed":
        print("✅ 今日答题已完成，不用重复了！")
        return
    
    # 如果有进行中的，跳过（防止实时重大新闻+不定期抽查两个cron同时启动冲突）
    if state["today"] == today and state["status"] == "in_progress":
        print("🔄 已有进行中的答题，跳过本次，让现有答题先完成")
        return
    
    # 随机选题（排除已答对题；题库全部抽完后重置）
    wrong = load_wrong()
    correct = load_correct()
    wrong_ids = {w["id"] for w in wrong}
    correct_ids = set(correct)

    # 如果全部题库都已答对，重置记录重新开始
    all_ids = {q["id"] for q in questions}
    if correct_ids >= all_ids:
        save_correct([])
        correct_ids = set()
        print("🏁 恭喜！全部题库已答完一遍，重新开始循环！")

    selected = []
    # 错题优先抽（最多一半）
    wrong_pool = [q for q in questions if q["id"] in wrong_ids]
    if wrong_pool:
        n_from_wrong = min(len(wrong_pool), max(1, total_questions // 2))
        selected.extend(random.sample(wrong_pool, n_from_wrong))
    # 剩余从未答对+未错题中抽
    remaining_n = total_questions - len(selected)
    if remaining_n > 0:
        pool = [q for q in questions if q["id"] not in wrong_ids and q["id"] not in correct_ids]
        if pool:
            selected.extend(random.sample(pool, min(remaining_n, len(pool))))
        else:
            # 无可选题（说明正确+错题覆盖了全部题库），全部题库随机
            selected.extend(random.sample(questions, min(remaining_n, len(questions))))
    random.shuffle(selected)
    
    # 清除今天旧错题残留
    wrong = load_wrong()
    cleaned = [w for w in wrong if w.get("last_wrong", "")[:10] != today]
    if len(cleaned) != len(wrong):
        save_wrong(cleaned)
    
    state = {
        "today": today,
        "status": "in_progress",
        "questions": selected,
        "current_index": 0,
        "correct_count": 0,
        "total_asked": 0
    }
    save_state(state)
    
    print(f"🎯 自动答题开始（{len(selected)}题，含{len(selected)-remaining_n}道错题复习）")
    print(f"超时设置：每题最多等{poll_timeout}秒")
    print("---")
    
    # ===== 2. 逐题循环 =====
    deadline_start = _time.time()
    
    while state["current_index"] < len(state["questions"]):
        idx = state["current_index"]
        q = state["questions"][idx]
        qtype = q.get("type", 1)
        titles = q.get("itemsTitleArray", [])
        items = q.get("itemsDescArray", [])
        
        # 2a. 先发题目文本+按钮，图片发送不能阻塞出题
        if qtype == 3:
            keyboard = _build_judge_keyboard(idx)
        elif qtype == 2:
            keyboard = _build_multi_choice_keyboard(idx, titles, items)
        else:
            keyboard = _build_single_choice_keyboard(idx, titles, items)
        
        text = format_question(q, idx, file_info=None)
        success = _send_qq_c2c_message(text, keyboard)
        if success:
            print(f"[Q{idx+1}] ✅ 已发送（含按钮）")
        else:
            print(f"[Q{idx+1}] ⚠️ 发送失败")
            print("---")
            print(text)

        # 2b. 图片作为补充发送，失败/超时不影响答题按钮
        img_url = (q.get("url", "") or "").strip()
        if img_url:
            print(f"[Q{idx+1}] 补发配图…")
            _send_question_image_to_qq(img_url)
        
        # 2c. 轮询等用户答案
        deadline = _time.time() + poll_timeout
        answered = False
        while _time.time() < deadline:
            try:
                result = _check_button_answer_file()
                if result is not None:
                    # result = "ANSWER:X"
                    user_ans = result.split(":", 1)[1]
                    print(f"[Q{idx+1}] 收到答案：{user_ans}")
                    answered = True
                    break
            except Exception:
                pass
            _time.sleep(1.5)
        
        if not answered:
            print(f"[Q{idx+1}] ⏰ 超时未收到答案，跳过")
            state["current_index"] += 1
            save_state(state)
            continue
        
        # 2e. 处理答案
        correct = check_answer(q, user_ans)
        answer_text = get_answer_text(q)
        
        if correct:
            state["correct_count"] += 1
            state["total_asked"] += 1
            # 记录已答对题
            correct_list = load_correct()
            if q["id"] not in correct_list:
                correct_list.append(q["id"])
                save_correct(correct_list)
            # ✅ 从错题本移除（答对的题不再在当前循环出现）
            wrong = load_wrong()
            before = len(wrong)
            wrong = [w for w in wrong if w["id"] != q["id"]]
            if len(wrong) != before:
                save_wrong(wrong)
            print(f"[Q{idx+1}] ✅ 正确！{answer_text}")
            print(f"   💡 {q.get('answerSkillExplain', '')}")
        else:
            state["total_asked"] += 1
            wrong = load_wrong()
            found = False
            for w in wrong:
                if w["id"] == q["id"]:
                    w["count"] = w.get("count", 0) + 1
                    w["last_wrong"] = str(datetime.now())
                    found = True
                    break
            if not found:
                wrong.append({
                    "id": q["id"],
                    "question": q["question"],
                    "answer": q["answer"],
                    "answer_text": answer_text,
                    "explain": q.get("answerSkillExplain", ""),
                    "count": 1,
                    "last_wrong": str(datetime.now())
                })
            save_wrong(wrong)
            print(f"[Q{idx+1}] ❌ 错误！正确答案：{answer_text}")
            print(f"   💡 {q.get('answerSkillExplain', q.get('remark', ''))}")
        
        # 2f. 下一题
        state["current_index"] += 1
        save_state(state)
    
    # ===== 3. 答题完成 =====
    state["status"] = "completed"
    save_state(state)
    rate = state["correct_count"] / state["total_asked"] * 100 if state["total_asked"] > 0 else 0
    wrong_count = state["total_asked"] - state["correct_count"]
    elapsed = int(_time.time() - deadline_start)
    correct_total = len(load_correct())
    total_bank = len(questions)
    remaining = total_bank - correct_total
    print("---")
    print(f"🎉 答题完成！耗时{elapsed//60}分{elapsed%60}秒")
    print(f"📊 {state['correct_count']}/{state['total_asked']}正确（正确率{rate:.0f}%），错了{wrong_count}题已记入错题本")
    print(f"📚 错题总数：{len(load_wrong())}题 | 已累计答对{correct_total}题（共{total_bank}题库）")
    print("✅ 今日门禁已开，可以自由使用了！")
    # 发QQ通知完成
    summary = f"🎉 答题完成！{state['correct_count']}/{state['total_asked']}正确（正确率{rate:.0f}%）\n⏱ 耗时{elapsed//60}分{elapsed%60}秒\n📚 错题{len(load_wrong())}道 | 已刷{correct_total}/{total_bank}题"
    if remaining <= 0:
        summary += "\n🏁 恭喜全部题库刷完一遍！"
    _send_qq_c2c_message(summary)


def _check_button_answer_file():
    '''检查button_answer.json是否有有效答案（不依赖状态文件）'''
    path = BUTTON_ANSWER_FILE
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        question_index = data.get("question_index", 0)
        answer = data.get("answer", "")
        
        # 验证是否匹配当前题目
        state = load_state()
        if state["status"] != "in_progress":
            os.remove(path)
            return None
        
        idx = state["current_index"]
        if question_index != idx + 1:
            os.remove(path)
            return None
        
        # 有效答案
        os.remove(path)
        return "ANSWER:%s" % answer
    except Exception:
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 driving-quiz.py <status|quiz|start|answer|reset|wrong|correct|bypass|send|check-button|poll> [参数]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        cmd_status()
    elif cmd == "start":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_QUIZ_COUNT
        cmd_start(n)
    elif cmd == "answer":
        if len(sys.argv) < 3:
            print("❌ 用法: python3 driving-quiz.py answer <你的答案（如 A/B/C/D/ABD）>")
            sys.exit(1)
        cmd_answer(sys.argv[2])
    elif cmd == "reset":
        if len(sys.argv) > 2 and sys.argv[2] == "all":
            cmd_reset_all()
        else:
            cmd_reset()
    elif cmd == "wrong":
        cmd_wrong()
    elif cmd == "correct":
        cmd_correct()
    elif cmd == "bypass":
        cmd_bypass()
    elif cmd == "send":
        cmd_send()
    elif cmd == "check-button":
        cmd_check_button()
    elif cmd == "poll":
        timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 600
        cmd_poll(timeout)
    elif cmd == "quiz":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_QUIZ_COUNT
        timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 600
        cmd_quiz(n, timeout)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
