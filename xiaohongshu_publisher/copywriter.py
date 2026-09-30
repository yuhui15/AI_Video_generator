from __future__ import annotations

import json

import requests


MISTRAL_MODEL = "ministral-14b-2512"
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MAX_ATTEMPTS = 4
SITE_LINE = "想知道自己几分？去 yanzumeixue.com 测"
# 字数只算正文部分，不含末尾自动追加的网址推荐行。
BODY_MIN_CHARS = 100
BODY_MAX_CHARS = 150
# 给模型的目标区间比硬性区间窄一些，留出误差余量。
BODY_TARGET = (BODY_MIN_CHARS + 10, BODY_MAX_CHARS - 10)


def generate_copywriting(
    api_key: str,
    mode: str,
    category: str,
    creator_prompt: str,
) -> dict[str, str]:
    topic = f"“{category}”颜值对比" if mode == "comparison" else f"话题“{category}”"
    extra = f"\n补充要求：{creator_prompt.strip()}" if creator_prompt.strip() else ""
    prompt = (
        f"为小红书{topic}图文写文案。"
        f"正文分 2-3 段，段落之间换行，共 {BODY_TARGET[0]}-{BODY_TARGET[1]} 字。"
        "不用 Markdown，不写网址。"
        f"{extra}\n"
        '只返回 JSON：{"title":"标题（≤20字）","content":"正文"}'
    )
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            return _request_copywriting(api_key, prompt)
        except CopyLengthOutOfRange as exc:
            last_error = exc
            adjust = "更短" if exc.body_length > BODY_MAX_CHARS else "更长、更饱满"
            prompt += (
                f"\n\n上一次正文 {exc.body_length} 字，不符合要求，请重写得{adjust}，"
                f"严格控制在 {BODY_TARGET[0]}-{BODY_TARGET[1]} 字。"
            )
    assert last_error is not None
    raise last_error


class CopyLengthOutOfRange(RuntimeError):
    def __init__(self, body_length: int) -> None:
        super().__init__(
            f"生成正文 {body_length} 字（不含网址推荐），不在 {BODY_MIN_CHARS}-{BODY_MAX_CHARS} 字范围内，请重试。"
        )
        self.body_length = body_length


def _request_copywriting(api_key: str, prompt: str) -> dict[str, str]:
    try:
        response = requests.post(
            MISTRAL_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是小红书颜值话题的文案编辑。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 600,
                "response_format": {"type": "json_object"},
            },
            timeout=90,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]["content"]
        result = json.loads(message)
    except requests.RequestException as exc:
        raise RuntimeError(f"Mistral 文案生成请求失败：{exc}") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Mistral 返回了无法解析的文案结果：{exc}") from exc

    if not isinstance(result, dict):
        shape = type(result).__name__
        raise RuntimeError(f"Mistral 返回的文案应为 JSON 对象，实际为 {shape}。请重试。")

    title = _first_text(result, ("title", "标题"))
    content = _first_text(result, ("content", "正文", "文案", "body", "caption"))
    if not isinstance(title, str) or not isinstance(content, str):
        returned_fields = ", ".join(str(key) for key in result.keys()) or "无"
        raise RuntimeError(
            "Mistral 已返回 JSON，但未提供有效的标题和正文文本。"
            f"识别到的字段：{returned_fields}。请重试；如持续发生，请检查模型响应格式。"
        )
    title = title.strip()
    content = content.strip()
    if not title or len(title) > 20:
        raise RuntimeError("生成标题为空或超过 20 个字符，请调整要求后重试。")
    # 模型偶尔会自己写推荐语，统一去掉后再追加固定推荐行。
    body = "\n".join(line for line in content.splitlines() if "yanzumeixue" not in line).strip()
    if not body:
        raise RuntimeError("生成正文为空，请调整要求后重试。")
    if len(body) > BODY_MAX_CHARS:
        body = _trim_to_sentence(body) or body
    if not BODY_MIN_CHARS <= len(body) <= BODY_MAX_CHARS:
        raise CopyLengthOutOfRange(len(body))
    return {"title": title, "content": f"{body}\n{SITE_LINE}"}


def _trim_to_sentence(body: str) -> str | None:
    """模型常常略超字数：在不超上限的最后一个句末标点处截断，截断后仍需满足下限。"""
    cut = max(body.rfind(mark, 0, BODY_MAX_CHARS) for mark in "。！？!?…")
    if cut == -1:
        return None
    trimmed = body[: cut + 1].strip()
    return trimmed if len(trimmed) >= BODY_MIN_CHARS else None


def _first_text(result: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str):
            return value
    return None