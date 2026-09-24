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
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from collect_content import collect, collect_forum_text


DEFAULT_RSS = "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
ENGLISH_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
FALLBACK_RSS = "https://www.bing.com/news/search?q={query}&format=rss"
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


@dataclass
class PhotoAsset:
    title: str
    image_url: str
    page_url: str
    license: str


FORUM_URL = "https://forum.looksmaxxing.com/"


def allowed_by_robots(url: str, cache: dict[str, urllib.robotparser.RobotFileParser]) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(urljoin(origin, "/robots.txt"))
        try:
            parser.read()
        except OSError:
            return False
        cache[origin] = parser
    return cache[origin].can_fetch(USER_AGENT, url)


def search_forum_photos(limit: int) -> list[PhotoAsset]:
    """Collect public image metadata from allowed forum HTML pages only."""
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
    queue = [FORUM_URL]
    seen_pages: set[str] = set()
    assets: list[PhotoAsset] = []
    seen_images: set[str] = set()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    while queue and len(seen_pages) < 12 and len(assets) < limit:
        page_url = queue.pop(0)
        if page_url in seen_pages or not allowed_by_robots(page_url, robots_cache):
            continue
        seen_pages.add(page_url)
        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Warning: forum page unavailable: {page_url} ({exc})", file=sys.stderr)
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select("a[href]"):
            href = urljoin(page_url, str(link["href"])).split("#", 1)[0]
            parsed = urlparse(href)
            if parsed.netloc == urlparse(FORUM_URL).netloc and href not in seen_pages:
                if "/attachments/" not in parsed.path and "/login/" not in parsed.path:
                    queue.append(href)
        image_urls = []
        for tag in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
            if tag.get("content"):
                image_urls.append(urljoin(page_url, str(tag["content"])))
        image_urls.extend(
            urljoin(page_url, str(tag["src"]))
            for tag in soup.select("img[src]")
        )
        for image_url in image_urls:
            parsed = urlparse(image_url)
            if (
                parsed.netloc != urlparse(FORUM_URL).netloc
                or "/attachments/" in parsed.path
                or image_url in seen_images
                or not allowed_by_robots(image_url, robots_cache)
            ):
                continue
            seen_images.add(image_url)
            assets.append(
                PhotoAsset(
                    title=soup.title.get_text(" ", strip=True) if soup.title else "Looksmaxxing forum image",
                    image_url=image_url,
                    page_url=page_url,
                    license="unknown_verify_license_before_use",
                )
            )
            if len(assets) >= limit:
                break
        time.sleep(0.5)
    if not assets:
        raise RuntimeError(
            "论坛公开页面没有找到可抓取图片。该站 robots.txt 禁止 /attachments/，"
            "请把已获授权的图片手动放入 input_images/。"
        )
    return assets


def search_public_photos(limit: int) -> list[PhotoAsset]:
    """Use the configured public forum crawler for automatic image inputs."""
    return search_forum_photos(limit)


def download_photos(assets: list[PhotoAsset], work: Path) -> list[Path]:
    photos: list[Path] = []
    for index, asset in enumerate(assets):
        destination = work / f"photo_{index:03d}.jpg"
        response = requests.get(asset.image_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        destination.write_bytes(response.content)
        photos.append(destination)
    return photos


def make_photo_card(photo: Path, title: str, index: int, total: int, output: Path) -> None:
    image = Image.open(photo).convert("RGB")
    image.thumbnail((WIDTH, HEIGHT))
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (12, 16, 27))
    x = (WIDTH - image.width) // 2
    y = 130 + (HEIGHT - 260 - image.height) // 2
    canvas.paste(image, (x, y))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, WIDTH, 230), fill=(8, 12, 22, 220))
    draw.rectangle((0, HEIGHT - 300, WIDTH, HEIGHT), fill=(8, 12, 22, 220))
    draw.text((70, 70), f"LOOKSMAXXING  {index + 1:02d}/{total:02d}", font=font(38), fill=(95, 226, 190))
    title_lines = textwrap.wrap(title, width=14)
    y_text = HEIGHT - 250
    for line in reversed(title_lines):
        draw.text((70, y_text), line, font=font(62), fill="white", stroke_width=2, stroke_fill=(0, 0, 0))
        y_text -= 78
    canvas.convert("RGB").save(output, quality=92)


def build_photo_video(topic: str, work: Path, output: Path, bgm: Path, duration: int, count: int) -> None:
    assets = search_public_photos(count)
    photos = download_photos(assets, work)
    titles = [
        f"{topic}：超模风格参考",
        "Looksmaxxing 论坛图片参考",
        "超模肖像：发型与镜头表现",
        "Looksmaxxing 社区视觉案例",
        "仅作参考，不代表统一审美标准",
    ]
    cards: list[Path] = []
    audio = [work / f"empty_{index:03d}.wav" for index in range(len(photos))]
    for index, photo in enumerate(photos):
        card = work / f"photo_card_{index:03d}.jpg"
        make_photo_card(photo, titles[index % len(titles)], index, len(photos), card)
        cards.append(card)
    compose(cards, audio, output, work, duration, bgm)
    (output.parent / "photo_sources.json").write_text(
        json.dumps([asset.__dict__ for asset in assets], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def generate_hf_video_clips(scenes: list[Scene], work: Path) -> list[Path]:
    """Generate short text-to-video clips through Hugging Face Inference API."""
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("缺少 HF_TOKEN。请在 .env 中设置 Hugging Face User Access Token。")
    model = os.getenv(
        "HF_VIDEO_MODEL",
        "Lightricks/LTX-Video-0.9.8-13B-distilled",
    )
    provider = os.getenv("HF_PROVIDER", "auto")
    try:
        from huggingface_hub import InferenceClient
    except ImportError as exc:
        raise RuntimeError(
            "缺少 huggingface_hub，请运行 .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from exc
    client = InferenceClient(model=model, provider=provider, token=token, timeout=600)
    clips: list[Path] = []
    for index, scene in enumerate(scenes):
        prompt = (
            "Vertical 9:16 cinematic educational short video, tasteful editorial style, "
            "abstract adult male grooming and healthy lifestyle visuals, no real person likeness, "
            "no logos, no text, no medical claims. " + scene.narration
        )
        output = work / f"ai_scene_{index:03d}.mp4"
        try:
            video = client.text_to_video(prompt)
            video_bytes = video if isinstance(video, bytes) else bytes(video)
            if not video_bytes:
                raise RuntimeError("服务返回了空视频")
            output.write_bytes(video_bytes)
            clips.append(output)
        except Exception as exc:
            if isinstance(exc, KeyError) and exc.args == ("video",):
                detail = (
                    "Hugging Face 提供商没有返回视频字段。当前模型可能未被所选提供商支持，"
                    "或提供商需要额度/权限；请在 Hugging Face 模型页确认 Inference Providers 状态。"
                )
            else:
                detail = str(exc).strip()
            response = getattr(exc, "response", None)
            if response is not None:
                status = getattr(response, "status_code", "unknown")
                body = getattr(response, "text", "") or ""
                detail = f"HTTP {status}: {body[:1000]}".strip()
            if not detail:
                detail = repr(exc)
            raise RuntimeError(
                f"Hugging Face 视频生成失败（场景 {index + 1}，模型 {model}，provider={provider}）：{detail}"
            ) from exc
    return clips


def generate_local_video_clips(scenes: list[Scene], work: Path) -> list[Path]:
    """Generate short clips locally with the Hugging Face Wan Diffusers pipeline."""
    model = os.getenv("LOCAL_VIDEO_MODEL", "/content/models/Wan2.1-T2V-1.3B-Diffusers")
    model_path = Path(model)
    if not model_path.is_dir():
        raise RuntimeError(
            f"本地模型目录不存在：{model_path}。请先在 Colab 挂载或下载模型，"
            "再将 LOCAL_VIDEO_MODEL 设置为该目录。"
        )
    try:
        import torch
        from diffusers import WanPipeline
        from diffusers.utils import export_to_video
    except ImportError as exc:
        raise RuntimeError(
            "本地 AI 视频依赖未安装，请运行 .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("本地 Wan 视频生成需要 NVIDIA CUDA；当前 PyTorch 未检测到 CUDA。")
    width = int(os.getenv("LOCAL_VIDEO_WIDTH", "320"))
    height = int(os.getenv("LOCAL_VIDEO_HEIGHT", "576"))
    frames = int(os.getenv("LOCAL_VIDEO_FRAMES", "49"))
    steps = int(os.getenv("LOCAL_VIDEO_STEPS", "12"))
    dtype = torch.float16
    try:
        pipe = WanPipeline.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            local_files_only=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        pipe.vae.enable_slicing()
    except Exception as exc:
        raise RuntimeError(f"本地模型加载失败（{model}）：{exc}") from exc
    clips: list[Path] = []
    for index, scene in enumerate(scenes):
        prompt = (
            "cinematic vertical educational video, tasteful abstract adult grooming "
            "and healthy lifestyle visuals, no real person likeness, no logos, no text, "
            "no medical claims, " + scene.narration
        )
        output = work / f"ai_scene_{index:03d}.mp4"
        try:
            result = pipe(
                prompt=prompt,
                negative_prompt="blurry, distorted face, extra fingers, watermark, logo, text",
                width=width,
                height=height,
                num_frames=frames,
                guidance_scale=5.0,
                num_inference_steps=steps,
            )
            export_to_video(result.frames[0], str(output), fps=16)
            clips.append(output)
        except Exception as exc:
            raise RuntimeError(f"本地 Wan 视频生成失败（场景 {index + 1}）：{exc}") from exc
    return clips


def prepare_i2v_image(image_path: Path, width: int, height: int, output: Path) -> Path:
    image = Image.open(image_path).convert("RGB")
    source_ratio = image.width / image.height
    target_ratio = width / height
    if source_ratio > target_ratio:
        crop_width = int(image.height * target_ratio)
        left = (image.width - crop_width) // 2
        image = image.crop((left, 0, left + crop_width, image.height))
    else:
        crop_height = int(image.width / target_ratio)
        top = (image.height - crop_height) // 2
        image = image.crop((0, top, image.width, top + crop_height))
    image.resize((width, height), Image.Resampling.LANCZOS).save(output, quality=95)
    return output


def generate_local_i2v_video_clips(
    scenes: list[Scene],
    work: Path,
    image_dir: Path | None,
) -> list[Path]:
    """Generate Wan image-to-video clips from user-provided local images."""
    model = os.getenv("LOCAL_VIDEO_MODEL", "/content/models/Wan2.1-I2V-14B-480P-Diffusers")
    model_path = Path(model)
    if not model_path.is_dir():
        raise RuntimeError(
            f"本地 I2V 模型目录不存在：{model_path}。请先下载 "
            "Wan2.1-I2V-14B-480P-Diffusers 并设置 LOCAL_VIDEO_MODEL。"
        )
    try:
        import torch
        from diffusers import WanImageToVideoPipeline
        from diffusers.utils import export_to_video
    except ImportError as exc:
        raise RuntimeError(
            "本地 I2V 依赖未安装，请运行 pip install -r requirements.txt。"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("本地 Wan I2V 视频生成需要 NVIDIA CUDA；当前 PyTorch 未检测到 CUDA。")

    width = int(os.getenv("LOCAL_VIDEO_WIDTH", "320"))
    height = int(os.getenv("LOCAL_VIDEO_HEIGHT", "576"))
    frames = int(os.getenv("LOCAL_VIDEO_FRAMES", "49"))
    steps = int(os.getenv("LOCAL_VIDEO_STEPS", "12"))
    if image_dir is None or not image_dir.is_dir():
        raise RuntimeError(
            "I2V 必须提供本地图片目录，请将已获授权的图片放入 "
            "MyDrive/AI_Video_generator/input_images/。"
        )
    images = sorted(
        path for path in image_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not images:
        raise RuntimeError(f"I2V 图片目录为空：{image_dir}")
    prepared_images = [
        prepare_i2v_image(image, width, height, work / f"i2v_input_{index:03d}.jpg")
        for index, image in enumerate(images)
    ]
    try:
        pipe = WanImageToVideoPipeline.from_pretrained(
            str(model_path),
            torch_dtype=torch.float16,
            local_files_only=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        pipe.vae.enable_slicing()
    except Exception as exc:
        raise RuntimeError(f"本地 Wan I2V 模型加载失败（{model}）：{exc}") from exc

    clips: list[Path] = []
    for index, scene in enumerate(scenes):
        image = Image.open(prepared_images[index % len(prepared_images)]).convert("RGB")
        prompt = (
            "cinematic vertical educational fashion video, tasteful adult grooming "
            "and healthy lifestyle visuals, preserve the person's identity and clothing, "
            "natural subtle movement, no logos, no text, no medical claims. "
            + scene.narration
        )
        output = work / f"i2v_scene_{index:03d}.mp4"
        try:
            result = pipe(
                image=image,
                prompt=prompt,
                negative_prompt="blurry, distorted face, deformed body, extra fingers, "
                "watermark, logo, text, rapid camera shake",
                width=width,
                height=height,
                num_frames=frames,
                guidance_scale=5.0,
                num_inference_steps=steps,
            )
            export_to_video(result.frames[0], str(output), fps=16)
            clips.append(output)
        except Exception as exc:
            raise RuntimeError(f"本地 Wan I2V 视频生成失败（场景 {index + 1}）：{exc}") from exc
    return clips


def compose_ai_video(clips: list[Path], output: Path, work: Path, bgm: Path, max_duration: int) -> None:
    concat = work / "ai_concat.txt"
    concat.write_text(
        "\n".join(f"file '{clip.resolve().as_posix()}'" for clip in clips),
        encoding="utf-8",
    )
    merged = work / "ai_merged.mp4"
    commands = [
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-t", str(max_duration), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(merged)],
        ["ffmpeg", "-y", "-i", str(merged), "-stream_loop", "-1", "-i", str(bgm),
         "-t", str(max_duration), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)],
    ]
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"FFmpeg 无法合成 AI 视频：{error}") from exc


def fetch_articles(topic: str, max_articles: int, rss_url: str | None) -> list[Article]:
    articles: list[Article] = []
    seen: set[str] = set()
    queries = [f"looksmaxxing {topic}", f"looksmaxxing {topic.split()[0]}"] if not rss_url else [topic]
    urls = [rss_url] if rss_url else (
        [DEFAULT_RSS.format(query=quote_plus(query)) for query in queries]
        + [ENGLISH_RSS.format(query=quote_plus("looksmaxxing skincare hairstyle"))]
        + [FALLBACK_RSS.format(query=quote_plus("looksmaxxing " + topic))]
    )
    failures: list[str] = []
    for url in urls:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"},
                timeout=20,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except requests.RequestException as exc:
            failures.append(f"{url}: {exc}")
            continue
        if feed.bozo and not feed.entries:
            failures.append(f"{url}: invalid RSS ({feed.bozo_exception})")
            continue
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
            source_data = entry.get("source", {})
            source = str(source_data.get("title", "")) if hasattr(source_data, "get") else ""
            if not source:
                source = link.split("/")[2] if "://" in link else "公开 RSS"
            articles.append(Article(title, link, summary[:600], source))
            if len(articles) >= max_articles:
                return articles
    if failures:
        print("RSS sources failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
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


def collect_text_articles(
    topic: str,
    max_articles: int,
    rss_url: str | None,
) -> tuple[list[Article], list[str]]:
    records = (
        collect_forum_text(max_articles)
        if rss_url is None
        else collect(max_articles, delay=0.5, rss_url=rss_url, queries=("looksmaxxing",))
    )
    articles = [
        Article(record.title, record.url, record.summary, record.source)
        for record in records
        if record.text and len(record.text.strip()) >= 30
    ]
    if not articles:
        raise RuntimeError("采集结果没有可用于脚本生成的文字内容。")
    return articles, [record.text for record in records if record.text and len(record.text.strip()) >= 30]


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
    scenes = [
        Scene(
            "先看整体风格",
            f"今天参考{topic}。画面重点放在整体风格、姿态和镜头表现，不把外貌与人的价值绑定。",
            ["尊重个体差异", "避免不现实的审美标准"],
        )
    ]
    for article in articles[:4]:
        scenes.append(Scene(article.title[:24], article.summary[:100] or "这篇公开内容提供了一个值得核查的观点。", ["查看原文来源", "不要把单一观点当成医疗结论"]))
    if not articles:
        scenes.extend(
            [
                Scene("发型与轮廓表现", "观察发型、光线和角度如何影响画面表达，不代表真实外貌评价。", ["仅作视觉参考"]),
                Scene("镜头与姿态", "用自然的轻微动作和稳定镜头呈现人物，避免夸张或贬低性的表达。", ["保持自然动作"]),
            ]
        )
    scenes.append(
        Scene(
            "温和地行动",
            "把可持续的小习惯放在第一位。如果涉及皮肤、饮食或训练问题，请向合格专业人士咨询。",
            ["仅供教育参考", "来源链接见视频说明"],
        )
    )
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


def run_windows_tts(text: str, output: Path) -> bool:
    if os.name != "nt":
        return False
    text_file = output.with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$preferred = $env:WINDOWS_TTS_VOICE; "
        "$voice = $s.GetInstalledVoices() | Where-Object { "
        "$_.VoiceInfo.Name -eq $preferred -or $_.VoiceInfo.Culture.Name -like 'zh-*' } | "
        "Select-Object -First 1; "
        "if ($null -ne $voice) { $s.SelectVoice($voice.VoiceInfo.Name) }; "
        f"$s.SetOutputToWaveFile('{output.resolve()}'); "
        f"$s.Speak((Get-Content -Raw -LiteralPath '{text_file.resolve()}')); "
        "$s.Dispose()"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
            return True
        detail = result.stderr.strip() or result.stdout.strip() or "未找到可用的 Windows 语音"
        print(f"Warning: Windows TTS unavailable: {detail}", file=sys.stderr)
    except OSError as exc:
        print(f"Warning: Windows TTS unavailable: {exc}", file=sys.stderr)
    finally:
        text_file.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    return False


def run_tts(text: str, output: Path) -> bool:
    engine = os.getenv("TTS_ENGINE", "windows").lower()
    if engine == "windows":
        return run_windows_tts(text, output)
    if engine in {"none", "off", "disabled"}:
        return False
    try:
        import asyncio
        import edge_tts

        async def save() -> None:
            await edge_tts.Communicate(text, os.getenv("TTS_VOICE", "zh-CN-YunxiNeural")).save(str(output))

        asyncio.run(save())
        return output.exists() and output.stat().st_size > 0
    except Exception as exc:
        output.unlink(missing_ok=True)
        print(f"Warning: online TTS unavailable, continuing without narration: {exc}", file=sys.stderr)
        return False


def compose(
    cards: list[Path],
    audio: list[Path],
    output: Path,
    work: Path,
    max_duration: int,
    bgm: Path | None = None,
) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is required. Install it and ensure `ffmpeg` is in PATH.")
    clips: list[Path] = []
    for index, card in enumerate(cards):
        clip = work / f"clip_{index:03d}.mp4"
        duration = 5
        if audio[index].exists() and audio[index].stat().st_size > 0:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio[index])],
                capture_output=True, text=True, check=False,
            )
            try:
                duration = max(3, float(probe.stdout.strip()))
            except ValueError:
                pass
            command = ["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-i", str(audio[index]), "-t", str(duration), "-vf", "format=yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(clip)]
        elif bgm:
            command = [
                "ffmpeg", "-y", "-loop", "1", "-i", str(card),
                "-stream_loop", "-1", "-i", str(bgm), "-t", str(duration),
                "-map", "0:v:0", "-map", "1:a:0", "-vf", "format=yuv420p",
                "-c:v", "libx264", "-c:a", "aac", "-shortest", str(clip),
            ]
        else:
            command = ["ffmpeg", "-y", "-loop", "1", "-i", str(card), "-t", str(duration), "-vf", "format=yuv420p", "-c:v", "libx264", "-an", str(clip)]
        try:
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"FFmpeg 无法处理场景 {index + 1}：{error}") from exc
        clips.append(clip)
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in clips), encoding="utf-8")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-t", str(max_duration), "-c", "copy", str(output)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        error = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg 无法合并视频：{error}") from exc


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="护肤、发型与健康习惯")
    parser.add_argument("--rss-url")
    parser.add_argument("--max-articles", type=int, default=5)
    parser.add_argument("--output", default="output/looksmaxxing.mp4")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument(
        "--ai-video",
        action="store_true",
        help="使用 Hugging Face API 文本生视频模型，而不是字幕卡片",
    )
    parser.add_argument(
        "--local-ai-video",
        action="store_true",
        help="使用本地 Hugging Face Wan 模型生成视频",
    )
    parser.add_argument(
        "--local-i2v-video",
        action="store_true",
        help="使用本地 Wan I2V 模型，根据图片和文字生成视频",
    )
    parser.add_argument(
        "--i2v-image-dir",
        help="I2V 输入图片目录；图片必须由用户自行准备并确认有使用权",
    )
    parser.add_argument(
        "--photo-video",
        action="store_true",
        help="只用公开授权图片和标题制作视觉视频，不抓取文章文字",
    )
    parser.add_argument("--tts", action="store_true", help="启用 Windows 本地旁白，默认关闭")
    parser.add_argument("--no-tts", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--bgm",
        default=os.getenv("BGM_PATH", "music\\phonk.mp3"),
        help="本地背景音乐文件（默认 music\\phonk.mp3），会自动循环并裁剪",
    )
    parser.add_argument("--duration", type=int, default=60, help="最终视频最长时长（秒）")
    parser.add_argument("--max-scenes", type=int, default=6, help="最多生成多少个视频场景")
    args = parser.parse_args()
    if args.max_articles < 1 or args.max_articles > 20:
        parser.error("--max-articles must be between 1 and 20")
    if args.duration < 5 or args.duration > 600:
        parser.error("--duration must be between 5 and 600 seconds")
    if args.max_scenes < 1 or args.max_scenes > 10:
        parser.error("--max-scenes must be between 1 and 10")
    bgm = Path(args.bgm)
    if not bgm.is_file() or bgm.stat().st_size == 0:
        parser.error(f"必须提供有效的 BGM 文件，当前文件不存在或为空：{bgm}")
    output = Path(args.output)
    if output.parent.name.lower() == "output" and output.parent.exists():
        shutil.rmtree(output.parent)
    work = Path(args.output).parent / "work"
    work.mkdir(parents=True, exist_ok=True)
    if args.photo_video:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("照片视频合成需要 FFmpeg，请先安装并将 ffmpeg 加入 PATH。")
        build_photo_video(args.topic, work, output, bgm, args.duration, args.max_scenes)
        print(f"完成：{output.resolve()}")
        print(f"图片来源与许可证：{(output.parent / 'photo_sources.json').resolve()}")
        return 0
    if args.no_llm:
        articles, texts = [], []
    else:
        articles, texts = collect_text_articles(args.topic, args.max_articles, args.rss_url)
    scenes = fallback_scenes(args.topic, articles) if args.no_llm else call_llm(args.topic, articles, texts)
    scenes = scenes[:args.max_scenes]
    if args.local_i2v_video and args.local_ai_video:
        parser.error("--local-i2v-video 和 --local-ai-video 不能同时使用")
    if args.local_i2v_video:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("本地 I2V 视频合成需要 FFmpeg，请先安装并将 ffmpeg 加入 PATH。")
        image_dir = Path(args.i2v_image_dir) if args.i2v_image_dir else None
        if image_dir is not None and not image_dir.is_dir():
            parser.error(f"I2V 图片目录不存在：{image_dir}")
        clips = generate_local_i2v_video_clips(scenes, work, image_dir)
        compose_ai_video(clips, output, work, bgm, args.duration)
        (output.parent / "sources.json").write_text(
            json.dumps(
                [
                    {"title": article.title, "url": article.url, "source": article.source,
                     "text_used_for_script": text}
                    for article, text in zip(articles, texts)
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"完成：{output.resolve()}")
        print(f"来源清单：{(output.parent / 'sources.json').resolve()}")
        return 0
    if args.local_ai_video:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("本地 AI 视频合成需要 FFmpeg，请先安装并将 ffmpeg 加入 PATH。")
        clips = generate_local_video_clips(scenes, work)
        compose_ai_video(clips, output, work, bgm, args.duration)
        (output.parent / "sources.json").write_text(
            json.dumps(
                [
                    {"title": article.title, "url": article.url, "source": article.source,
                     "text_used_for_script": text}
                    for article, text in zip(articles, texts)
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"完成：{output.resolve()}")
        print(f"来源清单：{(output.parent / 'sources.json').resolve()}")
        return 0
    if args.ai_video:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("AI 视频合成需要 FFmpeg，请先安装并将 ffmpeg 加入 PATH。")
        clips = generate_hf_video_clips(scenes, work)
        compose_ai_video(clips, output, work, bgm, args.duration)
        (output.parent / "sources.json").write_text(
            json.dumps(
                [
                    {"title": article.title, "url": article.url, "source": article.source,
                     "text_used_for_script": text}
                    for article, text in zip(articles, texts)
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"完成：{output.resolve()}")
        print(f"来源清单：{(output.parent / 'sources.json').resolve()}")
        return 0
    cards, audio = [], []
    for index, scene in enumerate(scenes):
        card = work / f"card_{index:03d}.png"
        sound = work / f"voice_{index:03d}.wav"
        make_card(scene, index, len(scenes), card)
        if args.tts and not args.no_tts:
            run_tts(scene.narration, sound)
        cards.append(card)
        audio.append(sound)
    output.parent.mkdir(parents=True, exist_ok=True)
    compose(cards, audio, output, work, args.duration, bgm)
    (output.parent / "sources.json").write_text(
        json.dumps(
            [
                {"title": article.title, "url": article.url, "source": article.source,
                 "text_used_for_script": text}
                for article, text in zip(articles, texts)
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"完成：{output.resolve()}")
    print(f"来源清单：{(output.parent / 'sources.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
