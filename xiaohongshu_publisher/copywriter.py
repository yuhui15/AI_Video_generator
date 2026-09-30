from __future__ import annotations

import json
import re

import requests


MISTRAL_MODEL = "ministral-14b-2512"
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
MAX_ATTEMPTS = 4
TITLE_MAX_CHARS = 20
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
        "标题不要出现英文名，直接写中文标题（如“欧美男神的阳光颜值”）。\n"
        '只返回 JSON：{"title":"标题（≤20字）","content":"正文"}'
    )
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            return _request_copywriting(api_key, prompt)
        except CopyNeedsRetry as exc:
            last_error = exc
            prompt += f"\n\n{exc.feedback}"
    assert last_error is not None
    raise last_error


class CopyNeedsRetry(RuntimeError):
    """标题或正文长度不合规：带着给模型的修改意见重试。"""

    def __init__(self, message: str, feedback: str) -> None:
        super().__init__(message)
        self.feedback = feedback


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
    if not title:
        raise CopyNeedsRetry("生成标题为空，请重试。", "上一次没有给出标题，请补上标题。")
    # 模型常把英文人名塞进标题导致超长，重试也改不过来，直接缩短。
    title = _shorten_title(title)
    # 模型偶尔会自己写推荐语，统一去掉后再追加固定推荐行。
    body = "\n".join(line for line in content.splitlines() if "yanzumeixue" not in line).strip()
    # 模型偶尔仍会用 **加粗**，小红书会原样显示星号。
    body = body.replace("**", "").replace("__", "")
    if not body:
        raise RuntimeError("生成正文为空，请调整要求后重试。")
    if len(body) > BODY_MAX_CHARS:
        body = _trim_to_sentence(body) or body
    if not BODY_MIN_CHARS <= len(body) <= BODY_MAX_CHARS:
        adjust = "更短" if len(body) > BODY_MAX_CHARS else "更长、更饱满"
        raise CopyNeedsRetry(
            f"生成正文 {len(body)} 字（不含网址推荐），不在 {BODY_MIN_CHARS}-{BODY_MAX_CHARS} 字范围内，请重试。",
            f"上一次正文 {len(body)} 字，不符合要求，请重写得{adjust}，严格控制在 {BODY_TARGET[0]}-{BODY_TARGET[1]} 字。",
        )
    return {"title": title, "content": f"{body}\n{SITE_LINE}"}


def _shorten_title(title: str) -> str:
    """标题超长时按标点切分，尽量保留开头完整的几段；仍超长就直接截断。"""
    if len(title) <= TITLE_MAX_CHARS:
        return title
    pieces = re.split(r"(?<=[：:，,！!？?｜|—])", title)
    shortened = ""
    for piece in pieces:
        if len(shortened + piece) > TITLE_MAX_CHARS:
            break
        shortened += piece
    shortened = shortened.rstrip("：:，,｜|— ")
    return shortened if shortened else title[:TITLE_MAX_CHARS].rstrip()


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