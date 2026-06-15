---
name: qq-bot-image-quiz
description: Use when building QQ Bot quiz or gate flows in Hermes that need question images plus clickable InlineKeyboard buttons. Covers image upload, message ordering, callback polling, and fallbacks for QQ Markdown/media limits.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [qqbot, messaging, quiz, images, buttons, gateway]
    related_skills: [qq-bot-platform, knowledge-gate-system, hermes-agent]
---

# QQ Bot Image Quiz

## Overview

QQ Bot quiz flows often need both a reference image and clickable answer buttons. In practice, QQ's Bot API is stricter than it looks: Markdown messages with keyboards work, image messages work, but mixing image/Markdown/button payloads in one request can fail or render poorly.

Use the two-message pattern: send the question image first, then send the text and `InlineKeyboard` buttons immediately after it. Chat preview may look small, but the user can tap the image to view it full-screen while the answer buttons remain usable.

## When to Use

Use this skill when:

- A Hermes QQ Bot flow sends quiz, exam, driving-test, knowledge-gate, or approval questions.
- The question includes an image URL that should display in QQ instead of appearing as a raw link.
- The flow needs clickable `InlineKeyboard` answer buttons.
- You need robust fallback behavior when QQ image upload or media sending fails.

Don't use this for:

- Pure text questions with no media.
- Long-form documents where `MEDIA:` delivery is enough.
- Platforms other than QQ Bot unless their media/button constraints match this pattern.

## Decision Framework

Choose the delivery pattern based on the question content:

| Condition | Pattern |
|---|---|
| No image URL | Send one Markdown/button message. |
| Image URL exists and buttons are required | Send image as a separate message, then send Markdown/button message. |
| Image upload succeeds but message API rejects mixed payload | Keep the separate image-first pattern; do not combine image and keyboard. |
| Image download/upload fails | Include the original image URL in the text and still send buttons. |
| User says image preview is too small | Keep current pattern if tap-to-fullscreen works; otherwise generate a larger question-card image. |

## Implementation Pattern

### 1. Download the Image

Use `urllib.request` so the helper works in minimal Python environments:

```python
import base64
import mimetypes
import urllib.request


def download_image(url: str, timeout: int = 15) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Hermes-Agent/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        data = response.read()
    if not data:
        raise ValueError("empty image response")
    if not content_type.startswith("image/"):
        guessed = mimetypes.guess_type(url)[0]
        content_type = guessed or "image/jpeg"
    return data, content_type
```

### 2. Upload and Send Image Directly

For QQ Bot C2C, prefer the media endpoint mode that sends a single in-memory question image to the current chat (`srv_send_msg=True`) when available in the adapter/API layer. This avoids a second fragile mixed media request. Do not pass arbitrary local file paths to this helper; it should only handle image bytes downloaded from the current question's public image URL.

```python
def image_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def build_upload_payload(data: bytes, content_type: str) -> dict:
    return {
        "file_type": 1,
        "srv_send_msg": True,
        "file_data": image_to_base64(data),
        "file_info": {"mime_type": content_type},
    }
```

### 3. Send Text and Buttons After Image

After image delivery returns success, send the normal quiz message with Markdown and keyboard:

```python
body = {
    "msg_type": 2,
    "markdown": {"content": question_markdown},
    "keyboard": keyboard_dict,
}
```

For single-choice and true/false questions, set `click_limit: 1` and use one callback per answer. For multiple-choice questions, use toggle callbacks for each option and a final submit callback.

## Callback Polling Pattern

QQ button callbacks arrive asynchronously through the gateway, not through the original send request. A robust quiz flow needs a polling or event bridge:

1. Gateway receives `INTERACTION_CREATE`.
2. Adapter extracts `button_data`.
3. Adapter writes or forwards the answer event, for example to `button_answer.json`.
4. Quiz script polls that event source, validates the answer, and sends the next question.

Example polling command for a script-based gate:

```bash
cd ~/.hermes/scripts && python3 driving-quiz.py poll 900
```

Use one polling window per question. Stop polling once the quiz or gate is complete.

## Fallbacks

Always keep the quiz usable even if image delivery fails:

- If image download fails, send the original image URL in the question text.
- If upload succeeds but QQ message sending fails, do not retry forever; send text/buttons with the URL.
- If QQ returns HTTP 500 for a mixed image+keyboard Markdown payload, switch back to the two-message pattern.
- If the user reports the preview is small but tap-to-fullscreen works, keep the implementation simple.
- If tap-to-fullscreen is not enough, generate a large question-card image with PIL and send that before buttons.

## Common Pitfalls

1. **Trying to put image and keyboard in one Markdown message.** QQ may reject `msg_type: 7` or other mixed payloads with HTTP 500. Send image first, buttons second.

2. **Assuming image preview size is the final size.** QQ often shows a small chat preview, but tapping opens the full image. Validate with the user before adding image resizing complexity.

3. **Forgetting `base64`.** Upload helpers that send inline file data need `import base64`.

4. **Continuing to poll after the gate is complete.** Stop answer polling once the required question count is completed, or stale clicks can affect later runs.

5. **Leaking QQ credentials in examples or logs.** Redact app IDs only if necessary and always redact secrets/tokens/passwords. Skills should describe env var names, not actual secret values.

6. **Relying on `send_message` for rich QQ buttons/media.** The generic messaging tool may not pass QQ-specific `keyboard` or upload fields. Use the QQ Bot REST/adapter path for rich interactions.

## Verification Checklist

- [ ] Image URL questions send an actual QQ image message, not only a raw URL.
- [ ] The text/button question appears immediately after the image.
- [ ] Single-choice buttons produce one answer callback.
- [ ] Multiple-choice buttons support toggle plus submit.
- [ ] Image failure falls back to URL text and still allows answering.
- [ ] Completed gates stop polling and do not send extra questions.
- [ ] No credentials, tokens, or user OpenIDs are committed into the skill or code.

## One-Shot Recipe

When upgrading an existing QQ quiz script:

1. Add `download_image()` and upload/send-image helper functions.
2. In `send_question()`, detect `question.get("image")` or equivalent before building the text message.
3. Send the image first with direct media upload/send.
4. Send the existing Markdown+keyboard payload unchanged.
5. Test one image question in a real QQ chat.
6. Confirm the user can tap the preview to view full-screen and still click buttons.
7. Keep the URL fallback for failed media delivery.
