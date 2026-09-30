from __future__ import annotations

import json

import requests


MISTRAL_MODEL = "ministral-14b-2512"
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"
CONTENT_MIN_CHARS = 50
CONTENT_MAX_CHARS = 70
MAX_ATTEMPTS = 4
SITE_LINE = "想知道自己几分？去 yanzumeixue.com 测"
ROAST_MIN_CHARS = CONTENT_MIN_CHARS - len(SITE_LINE) - 1
ROAST_MAX_CHARS = CONTENT_MAX_CHARS - len(SITE_LINE) - 1
# 给模型的目标区间比硬性区间窄一些，留出误差余量。
ROAST_TARGET = (ROAST_MIN_CHARS + 3, ROAST_MAX_CHARS - 10)


def generate_copywriting(
    api_key: str,
    mode: str,
    category: str,
    group_counts: dict[str, int],
    creator_prompt: str,
) -> dict[str, str]:
    style_prompt = (
        "文风参考小红书爆火的“月老点评”：毒舌、犀利、一针见血，敢下极端结论，"
        "例如“典型的经济适用男”“扔进人堆里瞬间隐身”“别信什么有趣的灵魂”“这就是残酷现实”。"
        "这些例句只用来参考语气，禁止照抄或套用其中的词句，要结合内容类别写出新鲜的比喻。"
        "可以狠，但不带脏字、不做人身侮辱、不涉及地域/性别/身体缺陷歧视。"
        "绝对不要使用任何 Markdown 格式（如加粗 **、标题符等）。"
        f"正文写两句狠话：第一句下极端结论，第二句补刀或点出残酷现实，"
        f"合计 {ROAST_TARGET[0]}-{ROAST_TARGET[1]} 个字，两句之间换行。"
        "不要写网址或推荐语，系统会自动追加。"
    )
    if mode == "comparison":
        task_prompt = "撰写一篇适合小红书的高低颜值对比图文笔记，用一句狠话点破高低分差距。"
    else:
        task_prompt = "根据用户提供的话题撰写一篇适合小红书的图文笔记，核心围绕想知道自己颜值是什么水平。"
    prompt = (
        f"{task_prompt}\n{style_prompt}\n\n"
        f"内容类别：{category}\n"
        f"图片分组与数量：{json.dumps(group_counts, ensure_ascii=False)}\n"
        f"创作者补充要求：{creator_prompt.strip() or '无'}\n\n"
        '只返回 JSON 对象，且必须包含两个字符串字段："title" 和 "content"。'
        '格式示例：{"title":"标题","content":"正文"}。不要使用其他字段名，也不要返回 Markdown 代码块。'
        f"标题最多 20 个字符，正文 {ROAST_TARGET[0]}-{ROAST_TARGET[1]} 个字符。"
    )
    last_error: RuntimeError | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            return _request_copywriting(api_key, prompt)
        except CopyLengthOutOfRange as exc:
            last_error = exc
            adjust = "更短" if exc.roast_length > ROAST_MAX_CHARS else "更长、更饱满"
            prompt += (
                f"\n\n上一次正文只有狠话部分就 {exc.roast_length} 字，不符合要求，请重写得{adjust}，"
                f"严格控制在 {ROAST_TARGET[0]}-{ROAST_TARGET[1]} 字。"
            )
    assert last_error is not None
    raise last_error


class CopyLengthOutOfRange(RuntimeError):
    def __init__(self, roast_length: int) -> None:
        total = roast_length + len(SITE_LINE) + 1
        super().__init__(
            f"生成正文 {total} 字，不在 {CONTENT_MIN_CHARS}-{CONTENT_MAX_CHARS} 字范围内，请调整要求后重试。"
        )
        self.roast_length = roast_length


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
                        "content": "你是毒舌犀利、一针见血的小红书颜值点评文案编辑，敢说狠话但不带脏字、不搞歧视。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 300,
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
    roast = "\n".join(line for line in content.splitlines() if "yanzumeixue" not in line).strip()
    if not roast:
        raise RuntimeError("生成正文为空，请调整要求后重试。")
    if len(roast) > ROAST_MAX_CHARS:
        roast = _trim_to_sentence(roast) or roast
    if not ROAST_MIN_CHARS <= len(roast) <= ROAST_MAX_CHARS:
        raise CopyLengthOutOfRange(len(roast))
    return {"title": title, "content": f"{roast}\n{SITE_LINE}"}


def _trim_to_sentence(roast: str) -> str | None:
    """模型常常略超字数：在不超上限的最后一个句末标点处截断，截断后仍需满足下限。"""
    cut = max(roast.rfind(mark, 0, ROAST_MAX_CHARS) for mark in "。！？!?…")
    if cut == -1:
        return None
    trimmed = roast[: cut + 1].strip()
    return trimmed if len(trimmed) >= ROAST_MIN_CHARS else None


def _first_text(result: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str):
            return value
    return None