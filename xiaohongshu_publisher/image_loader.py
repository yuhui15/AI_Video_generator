from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PUBLISHER_DIR = Path(__file__).resolve().parent
PROMO_IMAGE_PATH = PUBLISHER_DIR / "assets" / "yanzumeixue_promo.png"


def _image_files(folder: Path, recursive: bool = False) -> list[Path]:
    if not folder.is_dir():
        return []
    candidates = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        (
            path
            for path in candidates
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in IMAGE_EXTENSIONS
            and not any(
                part.lower() in {"high", "low", ".git", ".venv", "venv", "env", "models", "music"}
                for part in path.relative_to(folder).parts[:-1]
            )
        ),
        key=lambda path: path.name.casefold(),
    )


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_names = ("msyhbd.ttc", "simhei.ttf", "arialbd.ttf") if bold else ("msyh.ttc", "simsun.ttf", "arial.ttf")
    for font_name in font_names:
        font_path = Path("C:/Windows/Fonts") / font_name
        if font_path.is_file():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def ensure_promo_image() -> Path:
    if PROMO_IMAGE_PATH.is_file():
        return PROMO_IMAGE_PATH

    PROMO_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1080, 1440
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    
    # 极简现代网页风格微渐变背景
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(248 - 12 * ratio),
            int(250 - 12 * ratio),
            int(252 - 8 * ratio),
        )
        draw.line((0, y, width, y), fill=color)

    # 模仿 yanzumeixue.com 的现代卡片 UI 容器
    draw.rounded_rectangle((80, 100, 1000, 1340), radius=32, fill="#ffffff", outline="#e2e8f0", width=2)
    
    # 顶部品牌 Tag
    draw.rounded_rectangle((140, 180, 320, 240), radius=20, fill="#eff6ff")
    draw.text((170, 195), "颜祖美学", font=_font(24, bold=True), fill="#2563eb")

    # 核心大标题（修正了“颜祖美学”错别字）
    draw.text((140, 320), "想知道自己颜值", font=_font(64, bold=True), fill="#0f172a")
    draw.text((140, 410), "是什么水平吗？", font=_font(64, bold=True), fill="#0f172a")

    # 说明小字
    draw.text((140, 530), "基于多维面部指标与智能算法分析", font=_font(28), fill="#64748b")
    draw.text((140, 580), "探索属于你的美学数据与风格定位", font=_font(28), fill="#64748b")

    # 模仿网站 UI 的高亮操作按钮
    draw.rounded_rectangle((140, 750, 940, 910), radius=20, fill="#2563eb")
    draw.text((215, 805), "立即体验 yanzumeixue.com", font=_font(36, bold=True), fill="#ffffff")

    # 底部提示
    draw.text((140, 1100), "访问网站，解锁完整面部指标分析报告", font=_font(24), fill="#94a3b8")

    image.save(PROMO_IMAGE_PATH, format="PNG", optimize=True)
    return PROMO_IMAGE_PATH


def build_post_images(
    project_root: Path,
    mode: str,
    folder_path: str,
    count: int,
) -> tuple[list[Path], dict[str, int]]:
    folder = (project_root / folder_path).resolve()
    root = project_root.resolve()
    if folder == root or not folder.is_relative_to(root) or not folder.is_dir():
        raise ValueError("请选择项目目录中的有效图片文件夹。")
    if any(part.lower() in {".git", ".venv", "venv", "env", "__pycache__", "models", "music", "node_modules"} for part in Path(folder_path).parts):
        raise ValueError("不能从受保护的项目目录中抽取图片。")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("抽取数量必须是正整数。")

    selected: list[Path] = []
    group_counts: dict[str, int] = {}
    if mode == "comparison":
        if count > 8:
            raise ValueError("高低对比模式每个级别最多抽取 8 张（另加 1 张推广图）。")
        high_images = _image_files(folder / "high")
        low_images = _image_files(folder / "low")
        if len(high_images) < count or len(low_images) < count:
            raise ValueError(
                f"图片数量不足：high 有 {len(high_images)} 张，low 有 {len(low_images)} 张，"
                f"每组需要 {count} 张。"
            )
        selected = random.sample(high_images, count) + random.sample(low_images, count)
        group_counts = {"high": count, "low": count}
    elif mode == "topic":
        if count > 17:
            raise ValueError("话题模式最多抽取 17 张（另加 1 张推广图）。")
        images = _image_files(folder, recursive=True)
        if len(images) < count:
            raise ValueError(f"所选文件夹只有 {len(images)} 张照片，无法抽取 {count} 张。")
        selected = random.sample(images, count)
        group_counts = {"topic": count}
    else:
        raise ValueError("不支持的发布素材模式。")

    promo_image = ensure_promo_image()
    if len(selected) + 1 > 18:
        raise ValueError("图片总数超过平台单篇图文笔记的 18 张限制。")
    return [*selected, promo_image], group_counts