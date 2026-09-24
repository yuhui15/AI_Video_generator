# Looksmaxxing AI Video Generator

一个将公开网页中的 looksmaxxing 相关内容整理成短视频的 Python MVP：

1. 从 Google News RSS（中文和英文查询）获取公开文章，不可用时回退到 Bing News RSS，或使用自定义 RSS
2. 提取文章正文、去重并保留来源链接
3. 使用 OpenAI-compatible API 改写为 60 秒以内的中文短视频脚本
4. 默认生成无旁白视频，也可选择 Windows 本地旁白
5. 可选加入本地 BGM，自动循环并裁剪到视频长度
6. 必须使用本地 BGM，生成 9:16 竖屏字幕卡片并用 FFmpeg 合成为 MP4

也可以单独运行公开内容采集器，覆盖 PSL、looksmaxxing、clavicular、top model、护肤、发型和健身等关键词。它只保存公开页面正文、来源链接和图片链接/缩略图元数据，不下载原图：

```powershell
python collect_content.py --max-articles 30
```

输出到 `output\collection\articles.jsonl` 和 `output\collection\images.json`。采集器遵守 `robots.txt`、请求间隔和公开访问边界；不会绕过登录、验证码、付费墙或站点反爬限制。图片的授权状态默认标记为 `unknown_verify_license_before_use`，发布前必须逐条核验。

> 本工具只处理公开网页，不绕过登录、付费墙或反爬措施。发布前请确认文章、图片、音乐和声音的授权，并保留来源。内容提示词要求避免外貌羞辱、极端节食、危险药物和未经证实的医疗建议。

## 快速开始

需要 Python 3.10+ 和 FFmpeg（`ffmpeg` 必须在 PATH 中）。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate_video.py --topic "男士基础护肤和发型"
```

视频默认输出到 `output\looksmaxxing.mp4`，中间文件保存在 `output\work\`，实际送入 LLM 的文字和来源保存在 `output\sources.json`。

## 使用 LLM 和中文旁白

复制 `.env.example` 为 `.env`，填入 OpenAI 或其他 OpenAI-compatible 服务：

```text
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
TTS_VOICE=zh-CN-YunxiNeural
TTS_ENGINE=windows
WINDOWS_TTS_VOICE=
```

默认不生成旁白。添加 `--tts` 才会启用 Windows 本地语音，不需要访问微软 Edge TTS 网络服务。`WINDOWS_TTS_VOICE` 留空时会自动选择已安装的中文语音。没有 `OPENAI_API_KEY` 时会使用安全的本地模板脚本。

## 常用参数

```powershell
python generate_video.py --topic "护肤误区" --max-articles 5 --duration 60 --bgm "music\phonk.mp3"
python generate_video.py --rss-url "https://example.com/feed.xml"
python generate_video.py --no-llm --bgm "music\phonk.mp3" --output output\demo.mp4
python generate_video.py --ai-video --bgm "music\phonk.mp3" --output output\ai-demo.mp4
python generate_video.py --local-ai-video --no-llm --max-articles 1 --max-scenes 1 --duration 5
python generate_video.py --photo-video --topic "looksmaxxing top model" --max-scenes 5 --duration 30 --bgm "music\phonk.mp3"
python generate_video.py --no-llm --tts --output output\voice-demo.mp4
```

使用 `--bgm` 时请提供本地、已获授权的 MP3/WAV 等音乐文件。程序不会自动下载或内置流行歌曲。BGM 会自动循环并裁剪到视频长度。Windows 本地语音由系统语音包提供，可在 Windows 设置的“时间和语言 → 语音”中安装中文语音。

每次运行 `generate_video.py` 都会先清空默认的 `output\` 目录，然后重新抓取文字、生成脚本和视频。默认使用 `music\phonk.mp3`；也可以通过 `--bgm` 或 `BGM_PATH` 指定其他本地音乐。

## 免费在线 AI 视频

在 Hugging Face 创建 User Access Token 后，只在本机 `.env` 中填写：

```text
HF_TOKEN=hf_你的Token
HF_VIDEO_MODEL=Lightricks/LTX-Video-0.9.8-13B-distilled
HF_PROVIDER=auto
```

然后运行：

```powershell
python generate_video.py --ai-video --topic "男士基础护肤和发型" --duration 30
```

`--ai-video` 会把 LLM 生成的每个场景提示词发送给 Hugging Face Inference Providers，再与本地 BGM 合成。`HF_PROVIDER=auto` 会自动选择支持该模型的提供商；Wan 模型通常不由旧的 `hf-inference` 提供商直接托管。免费额度、提供商可用性和排队时间会变化，部分提供商可能需要账户额度。不要把 `HF_TOKEN` 提交到 GitHub。

## Hugging Face API 视频模式

当前推荐使用 Hugging Face API，不会在本机下载视频模型权重。确保 `.env` 中有：

```text
HF_TOKEN=hf_你的Token
HF_PROVIDER=auto
HF_VIDEO_MODEL=Lightricks/LTX-Video-0.9.8-13B-distilled
```

运行：

```powershell
.\.venv\Scripts\python.exe generate_video.py --ai-video --topic "男士基础护肤和发型" --max-scenes 1 --duration 5 --bgm "music\phonk.mp3"
```

`--local-ai-video` 仍保留为文字生视频模式。图片加文字请使用 `--local-i2v-video`，它加载 `Wan2.1-I2V-14B-480P-Diffusers`，并将每个场景的输入图片与提示词一起传给模型。可以用 `--i2v-image-dir` 指定本地图片目录；不指定时，程序会按主题下载 Wikimedia Commons 缩略图，并把来源保存到 `output\work\i2v_sources.json`。运行前请在 Colab 下载或挂载模型，并将 `LOCAL_VIDEO_MODEL` 设置为本地模型目录；程序使用 `local_files_only=True`，不会自动下载模型。

## Google Colab + Google Drive

仓库提供了 [colab_run.py](./colab_run.py)，用于在 Colab 中挂载 Drive、clone 或更新本仓库、安装 FFmpeg 和 Python 依赖，并从 Drive 加载已经下载好的 Wan 模型。脚本不会自动下载模型，也不会把 API key 写入仓库。

在 Colab 单元格中分两步运行。先在 Notebook 主进程中挂载 Drive：

```python
from google.colab import drive
drive.mount("/content/drive")
```

然后再 clone 并运行脚本：

```python
%cd /content
!rm -rf AI_Video_generator
!git clone https://github.com/yuhui15/AI_Video_generator.git
!python /content/AI_Video_generator/colab_run.py
```

首次运行前，将模型放到：

```text
MyDrive/models/Wan2.1-I2V-14B-480P-Diffusers/
```

并将 BGM 放到：

```text
MyDrive/AI_Video_generator/music/phonk.mp3
```

如果仓库已经在 Drive 中，脚本会执行 `git pull --ff-only`。视频输出到：

```text
MyDrive/AI_Video_generator/output/colab_wan.mp4
```

Colab 默认使用图片加文字的 I2V 模式。将自己的 JPG、PNG 或 WEBP 图片放到：

```text
MyDrive/AI_Video_generator/input_images/
```

如果该目录为空或不存在，程序会只使用“supermodel”或“looksmaxxing forum”关键词从 Wikimedia Commons 搜索缩略图。程序不会绕过论坛登录、验证码、robots.txt 或反爬限制；论坛图片的授权和肖像权也不确定，因此如需使用特定论坛图片，请先确认许可后手动放入 `input_images`。首次下载模型可以在 Colab 中执行：

```python
from huggingface_hub import snapshot_download
snapshot_download(
    "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers",
    local_dir="/content/drive/MyDrive/models/Wan2.1-I2V-14B-480P-Diffusers",
)
```

14B I2V 模型需要较多磁盘、系统内存和显存。Colab 入口默认生成 4 个约 5 秒的场景，合成为约 20 秒的视频；Wan I2V 不适合一次直接生成 20 秒单镜头。如果显存不足，降低 `LOCAL_VIDEO_WIDTH`、`LOCAL_VIDEO_HEIGHT`、`LOCAL_VIDEO_FRAMES` 或 `LOCAL_VIDEO_STEPS`。

## 图片驱动视频

如果视频模型只支持 `image-to-video`，可以使用 `--photo-video`。该模式不抓取文章正文，也不把网页文字送入 LLM；它只从 Wikimedia Commons 搜索公开图片，下载缩略图，叠加 looksmaxxing 主题标题并添加本地 BGM。图片页面、缩略图地址和许可证会保存到 `output\photo_sources.json`，发布前仍需遵守每张图片的署名和许可证要求。

## 内容边界

本项目用于教育和媒体制作，不是医疗或心理咨询工具。生成提示词明确要求：

- 不鼓励自残、极端减重、未成年人外貌改造或未经医生指导使用药物
- 不将外貌价值与人的价值绑定，不使用侮辱性标签
- 对护肤、训练和健康内容使用“可能/一般建议”等谨慎表述，并建议咨询专业人士
- 每条视频展示文章来源和“仅供教育参考”提示
