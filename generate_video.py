"""Generate a sourced, vertical educational video from public web articles."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont


DEFAULT_RSS = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
USER_AGENT = "LooksmaxxingVideoGenerator/1.0 (+public-content-only)"
WIDTH, HEIGHT = 1080, 1920


@dataclass
class Article:
    title: str
    url: str
    summary: str
    source: str


@dataclass
class Scene:
    title: str
    narration: str
    bullets: list[str]


def fetch_articles(topic: str, max_articles: int, rss_url: str | None) -> list[Article]:
    url = rss_url or DEFAULT_RSS.format(query=quote_plus(f"looksmaxxing {topic}"))
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    articles: list[Article] = []
    seen: set[str] = set()
    for entry in feed.entries:
        link = str(entry.get("link", "")).strip()
        title = BeautifulSoup(str(entry.get("title", "")), "html.parser").get_text(" ", strip=True)
        if not link or not title or link in seen:
            continue
        seen.add(link)
        summary = BeautifulSoup(
            str(entry.get("summary", entry.get("description", ""))),
            "html.parser",
        ).get_text(" ", strip=True)
        source = str(entry.get("source", {}).get("title", "")) or link.split("/")[2]
        articles.append(Article(title, link, summary[:600], source))
        if len(articles) >= max_articles:
            break
    return articles


def extract_text(article: Article) -> str:
    try:
        response = requests.get(article.url, headers={"User-Agent": USER_AGENT}, timeout=20)
        response.raise_for_status()
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        if text:
            return re.sub(r"\s+", " ", text).strip()[:5000]
    except requests.RequestException as exc:
        print(f"Warning: could not fetch {article.url}: {exc}", file=sys.stderr)
    return article.summary


def call_llm(topic: str, articles: list[Article], texts: list[str]) -> list[Scene]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_scenes(topic, articles)
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是严谨的中文短视频编导。只根据给定来源写教育性内容。"
                    "不要外貌羞辱、极端节食、危险药物、未成年人改造或未经证实的医疗建议。"
                    "不把外貌和人的价值绑定。输出 JSON：{\"scenes\":["
                    "{\"title\":\"...\",\"narration\":\"...\",\"bullets\":[\"...\",\"...\"]}]}"
                    "，4-6 个场景，每个旁白不超过 80 个汉字。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"topic": topic, "sources": [
                        {"title": a.title, "url": a.url, "text": t}
                        for a, t in zip(articles, texts)
                    ]},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        scenes = [
            Scene(str(item["title"]), str(item["narration"]), [str(x) for x in item.get("bullets", [])[:3]])
            for item in data["scenes"]
        ]
        if scenes:
            return scenes
    except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Warning: LLM unavailable, using template script: {exc}", file=sys.stderr)
    return fallback_scenes(topic, articles)


def fallback_scenes(topic: str, articles: list[Article]) -> list[Scene]:
    scenes = [Scene("先说结论", f"今天聊聊{topic}。改善状态可以从规律作息、基础清洁和适度运动开始，不必追求不现实的标准。", ["尊重个体差异", "优先选择低风险习惯"])]
    for article in articles[:4]:
        scenes.append(Scene(article.title[:24], article.summary[:100] or "这篇公开内容提供了一个值得核查的观点。", ["查看原文来源", "不要把单一观点当成医疗结论"]))
    scenes.append(Scene("温和地行动", "把可持续的小习惯放在第一位。如果涉及皮肤、饮食或训练问题，请向合格专业人士咨询。", ["仅供教育参考", "来源链接见视频说明"]))
    return scenes


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_card(scene: Scene, index: int, total: int, output: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), (17 + index * 8 % 35, 25, 48 + index * 10 % 50))
    draw = ImageDraw.Draw(image)
    accent = (95, 226, 190)
    draw.rounded_rectangle((70, 110, 260, 190), 25, fill=accent)
    draw.text((105, 130), f"{index + 1:02d}/{total:02d}", font=font(38), fill=(5, 20, 25))
    draw.text((70, 350), "LOOKSMAXXING", font=font(42), fill=accent)
    title_lines = textwrap.wrap(scene.title, width=12)
    y = 470
    for line in title_lines:
        draw.text((70, y), line, font=font(80), fill="white", stroke_width=2, stroke_fill=(0, 0, 0))
        y += 105
    y += 70
    for bullet in scene.bullets:
        for line in textwrap.wrap("• " + bullet, width=20):
            draw.text((80, y), line, font=font(42), fill=(220, 235, 235))
            y += 62
        y += 18
    draw.text((70, 1660), "仅供教育参考 · 不替代专业建议", font=font(30), fill=(180, 195, 200))
    image.save(output)


def run_tts(text: str, output: Path) -> bool:
    try:
        import asyncio
        import edge_tts

        async def save() -> None:
            await edge_tts.Communicate(text, os.getenv("TTS_VOICE", "zh-CN-YunxiNeural")).save(str(output))

        asyncio.run(save())
        return output.exists()
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"Warning: TTS unavailable, continuing without narration: {exc}", file=sys.stderr)
        return False


def compose(cards: list[Path], audio: list[Path], output: Path, work: Path, max_duration: int) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required. Install it and ensure `ffmpeg` is in PATH.")
    clips: list[Path] = []
    for index, card in enumerate(cards):
        clip = work / f"clip_{index:03d}.mp4"
        duration = 5
        if audio[index].exists():
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio[index])],
                capture_output=True, text=True, check=False,
            )
            try:
                duration = max(3, float(probe.stdout.strip()))
            except ValueError:
                pass
            command = ["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-i", str(audio[index]), "-t", str(duration), "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(clip)]
        else:
            command = ["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-t", str(duration), "-vf", "format=yuv420p", "-c:v", "libx264", "-an", str(clip)]
        subprocess.run(command, check=True, capture_output=True)
        clips.append(clip)
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in clips), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-t", str(max_duration), "-c", "copy", str(output)],
        check=True,
        capture_output=True,
    )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="护肤、发型与健康习惯")
    parser.add_argument("--rss-url")
    parser.add_argument("--max-articles", type=int, default=5)
    parser.add_argument("--output", default="output/looksmaxxing.mp4")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--duration", type=int, default=60, help="最终视频最长时长（秒）")
    args = parser.parse_args()
    if args.max_articles < 1 or args.max_articles > 20:
        parser.error("--max-articles must be between 1 and 20")
    if args.duration < 5 or args.duration > 600:
        parser.error("--duration must be between 5 and 600 seconds")
    work = Path(args.output).parent / "work"
    work.mkdir(parents=True, exist_ok=True)
    articles = fetch_articles(args.topic, args.max_articles, args.rss_url)
    if not articles:
        raise RuntimeError("没有获取到公开文章，请检查网络或 RSS 地址。")
    texts = [extract_text(article) for article in articles]
    scenes = fallback_scenes(args.topic, articles) if args.no_llm else call_llm(args.topic, articles, texts)
    cards, audio = [], []
    for index, scene in enumerate(scenes):
        card = work / f"card_{index:03d}.png"
        sound = work / f"voice_{index:03d}.mp3"
        make_card(scene, index, len(scenes), card)
        run_tts(scene.narration, sound)
        cards.append(card)
        audio.append(sound)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    compose(cards, audio, output, work, args.duration)
    (output.parent / "sources.json").write_text(json.dumps([a.__dict__ for a in articles], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成：{output.resolve()}")
    print(f"来源清单：{(output.parent / 'sources.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
