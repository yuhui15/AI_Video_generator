"""Google Colab entry point for the local Wan video pipeline.

Run this file from a Colab cell after setting the variables in the configuration
section below. Secrets are read from Colab environment variables or prompted at
runtime; they are never written to the repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/yuhui15/AI_Video_generator.git"
DRIVE_ROOT = Path("/content/drive/MyDrive")
REPO_DIR = DRIVE_ROOT / "AI_Video_generator"
MODEL_DIR = DRIVE_ROOT / "models/Wan2.1-T2V-1.3B-Diffusers"
BGM_PATH = REPO_DIR / "music/phonk.mp3"

TOPIC = "男士基础护肤和发型"
MAX_ARTICLES = 1
MAX_SCENES = 1
DURATION = 5


def run(command: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def mount_drive() -> None:
    try:
        from google.colab import drive
    except ImportError as exc:
        raise RuntimeError("请在 Google Colab 中运行此脚本。") from exc
    drive.mount("/content/drive")


def clone_or_update_repo() -> None:
    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    if (REPO_DIR / ".git").is_dir():
        run(["git", "pull", "--ff-only"], cwd=REPO_DIR)
    elif REPO_DIR.exists():
        raise RuntimeError(f"目标目录已存在但不是 Git 仓库：{REPO_DIR}")
    else:
        run(["git", "clone", REPO_URL, str(REPO_DIR)])


def install_runtime_dependencies() -> None:
    run(["apt-get", "update", "-qq"])
    run(["apt-get", "install", "-y", "-qq", "ffmpeg"])
    run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=REPO_DIR)


def configure_environment() -> None:
    if not MODEL_DIR.is_dir():
        raise RuntimeError(
            f"模型目录不存在：{MODEL_DIR}\n"
            "请先把 Wan2.1-T2V-1.3B-Diffusers 放到 Google Drive 的 models 目录。"
        )
    if not BGM_PATH.is_file():
        raise RuntimeError(f"BGM 文件不存在：{BGM_PATH}")

    os.environ["LOCAL_VIDEO_MODEL"] = str(MODEL_DIR)
    os.environ.setdefault("LOCAL_VIDEO_WIDTH", "320")
    os.environ.setdefault("LOCAL_VIDEO_HEIGHT", "576")
    os.environ.setdefault("LOCAL_VIDEO_FRAMES", "49")
    os.environ.setdefault("LOCAL_VIDEO_STEPS", "12")

    if not os.getenv("OPENAI_API_KEY"):
        print("未设置 OPENAI_API_KEY，将使用本地模板脚本。")


def generate() -> None:
    output = REPO_DIR / "output/colab_wan.mp4"
    command = [
        sys.executable,
        "generate_video.py",
        "--local-ai-video",
        "--topic",
        TOPIC,
        "--max-articles",
        str(MAX_ARTICLES),
        "--max-scenes",
        str(MAX_SCENES),
        "--duration",
        str(DURATION),
        "--no-tts",
        "--bgm",
        str(BGM_PATH),
        "--output",
        str(output),
    ]
    run(command, cwd=REPO_DIR)
    print(f"视频已生成：{output}")


def main() -> None:
    mount_drive()
    clone_or_update_repo()
    install_runtime_dependencies()
    configure_environment()
    generate()


if __name__ == "__main__":
    main()
