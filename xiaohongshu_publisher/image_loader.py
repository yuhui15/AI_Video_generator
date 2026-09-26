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
    font_names = ("msyhbd.ttc", "simhei.ttf", "arialbd.ttf") if bold else ("msyh.ttc", "simsun.ttc", "arial.ttf")
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
    image = Image.new("RGB", (width, height), "#111923")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(23 + 29 * ratio),
            int(36 + 27 * ratio),
            int(50 + 20 * ratio),
        )
        draw.line((0, y, width, y), fill=color)
    draw.ellipse((650, -220, 1320, 450), fill="#25445a")
    draw.ellipse((-250, 930, 500, 1680), fill="#1b3445")
    draw.rounded_rectangle((96, 100, 984, 1340), radius=24, outline="#7d9aaa", width=3)
    draw.text((150, 250), "YANZU", font=_font(38, bold=True), fill="#b7c8d0")
    draw.line((150, 315, 930, 315), fill="#8197a3", width=2)
    draw.text((150, 470), "彦祖美学", font=_font(92, bold=True), fill="#f4f1e9")
    draw.text((155, 620), "让美学研究更有方向", font=_font(38), fill="#d2dce0")
    draw.text((155, 875), "探索面部美学与影像表达", font=_font(32), fill="#c1d0d6")
    draw.rounded_rectangle((150, 1050, 930, 1165), radius=12, fill="#e9e6dc")
    draw.text((200, 1080), "了解更多  ·  yanzumeixue.com", font=_font(36, bold=True), fill="#182530")
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
