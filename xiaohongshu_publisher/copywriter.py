from __future__ import annotations

import json

import requests


MISTRAL_MODEL = "ministral-14b-2512"
MISTRAL_CHAT_URL = "https://api.mistral.ai/v1/chat/completions"


def generate_copywriting(
    api_key: str,
    mode: str,
    category: str,
    group_counts: dict[str, int],
    creator_prompt: str,
) -> dict[str, str]:
    if mode == "comparison":
        required_prompt = (
            "撰写一篇适合小红书的高低对比图文笔记。清楚说明 high 与 low 代表本组图片的分类，"
            "围绕用户提供的美学指标进行中性、尊重的视觉观察；不要羞辱、诊断或断言个人价值，"
            "不要把图片当作科学测量结论。结构包含简短标题、正文和少量相关话题标签。"
        )
    else:
        required_prompt = (
            "根据用户提供的话题和创作者要求撰写一篇适合小红书的图文笔记，包含简短标题、"
            "有信息量的正文和少量相关话题标签。不要编造图片中无法确认的事实。"
        )
    prompt = (
        f"{required_prompt}\n\n"
        f"内容类别：{category}\n"
        f"图片分组与数量：{json.dumps(group_counts, ensure_ascii=False)}\n"
        f"创作者补充要求：{creator_prompt.strip() or '无'}\n\n"
        '只返回 JSON 对象，且必须包含两个字符串字段："title" 和 "content"。'
        '格式示例：{"title":"标题","content":"正文"}。不要使用其他字段名，也不要返回 Markdown 代码块。'
        "标题最多 20 个字符，正文最多 1000 个字符。"
    )
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
                        "content": "你是谨慎、准确、尊重用户的中文社交媒体文案编辑。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 900,
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
    if not content or len(content) > 1000:
        raise RuntimeError("生成正文为空或超过 1000 个字符，请调整要求后重试。")
    return {"title": title, "content": content}


def _first_text(result: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str):
            return value
    return None
