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
                part.lower() in {"数值高", "数值低", ".git", ".venv", "venv", "env", "models", "music"}
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
    image = Image.new("RGB", (width, height), "#0f172a")
    draw = ImageDraw.Draw(image)
    
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = (
            int(15 + 10 * ratio),
            int(23 + 15 * ratio),
            int(42 + 20 * ratio),
        )
        draw.line((0, y, width, y), fill=color)

    draw.rounded_rectangle((70, 80, 1010, 1360), radius=28, fill="#1e293b", outline="#334155", width=2)
    
    draw.rounded_rectangle((130, 150, 380, 215), radius=16, fill="#3b82f6")
    draw.text((155, 168), "颜祖美学 · 颜问", font=_font(22, bold=True), fill="#ffffff")

    draw.text((130, 280), "想知道自己颜值", font=_font(60, bold=True), fill="#f8fafc")
    draw.text((130, 360), "是什么水平吗？", font=_font(60, bold=True), fill="#38bdf8")

    draw.text((130, 470), "AI 驱动的专业颜值评测与量化分析平台", font=_font(26, bold=True), fill="#94a3b8")
    
    features = [
        ("100+ 硬核维度", "多维面部指标解码分析"),
        ("四大支柱体系", "结构、和谐度、轮廓、二态性"),
    ]
    card_y = 550
    for title_txt, desc_txt in features:
        draw.rounded_rectangle((130, card_y, 950, card_y + 90), radius=12, fill="#0f172a", outline="#475569", width=1)
        draw.text((160, card_y + 18), title_txt, font=_font(24, bold=True), fill="#38bdf8")
        draw.text((160, card_y + 52), desc_txt, font=_font(20), fill="#94a3b8")
        card_y += 110

    draw.rounded_rectangle((130, 930, 950, 1060), radius=18, fill="#2563eb")
    draw.text((220, 972), "立即体验 yanzumeixue.com", font=_font(34, bold=True), fill="#ffffff")

    draw.text((130, 1160), "客观评测 · 专属形象顾问 · 科学重塑形象", font=_font(22), fill="#64748b")
    draw.text((130, 1200), "访问网站解锁你的个性化提升方案", font=_font(22), fill="#64748b")

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
        raise ValueError("挑选数量必须是正整数。")

    selected: list[Path] = []
    group_counts: dict[str, int] = {}
    if mode == "comparison":
        if count > 8:
            raise ValueError("数值高和数值低对比模式每个级别最多抽取 8 张（另加 1 张推广图）。")
        
        high_images = _image_files(folder / "数值高")
        low_images = _image_files(folder / "数值低")
        
        if len(high_images) < count or len(low_images) < count:
            raise ValueError(
                f"图片数量不足：数值高文件夹有 {len(high_images)} 张，数值低文件夹有 {len(low_images)} 张，"
                f"每组需要 {count} 张。"
            )
        selected = random.sample(high_images, count) + random.sample(low_images, count)
        group_counts = {"数值高": count, "数值低": count}
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