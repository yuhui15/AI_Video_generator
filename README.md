# Looksmaxxing AI Video Generator

一个将公开网页中的 looksmaxxing 相关内容整理成短视频的 Python MVP：

1. 从 Google News RSS（或自定义 RSS）获取公开文章
2. 提取文章正文、去重并保留来源链接
3. 使用 OpenAI-compatible API 改写为 60 秒以内的中文短视频脚本
4. 使用 Edge TTS 生成旁白
5. 生成 9:16 竖屏字幕卡片，并用 FFmpeg 合成为 MP4

> 本工具只处理公开网页，不绕过登录、付费墙或反爬措施。发布前请确认文章、图片、音乐和声音的授权，并保留来源。内容提示词要求避免外貌羞辱、极端节食、危险药物和未经证实的医疗建议。

## 快速开始

需要 Python 3.10+ 和 FFmpeg（`ffmpeg` 必须在 PATH 中）。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python generate_video.py --topic "男士基础护肤和发型"
```

视频默认输出到 `output\looksmaxxing.mp4`，中间文件保存在 `output\work\`。

## 使用 LLM 和中文旁白

复制 `.env.example` 为 `.env`，填入 OpenAI 或其他 OpenAI-compatible 服务：

```text
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
TTS_VOICE=zh-CN-YunxiNeural
```

没有 `OPENAI_API_KEY` 时会使用安全的本地模板脚本；没有 `edge-tts` 或网络不可用时会生成无旁白视频而不是静默失败。

## 常用参数

```powershell
python generate_video.py --topic "护肤误区" --max-articles 5 --duration 60
python generate_video.py --rss-url "https://example.com/feed.xml"
python generate_video.py --no-llm --output output\demo.mp4
```

## 内容边界

本项目用于教育和媒体制作，不是医疗或心理咨询工具。生成提示词明确要求：

- 不鼓励自残、极端减重、未成年人外貌改造或未经医生指导使用药物
- 不将外貌价值与人的价值绑定，不使用侮辱性标签
- 对护肤、训练和健康内容使用“可能/一般建议”等谨慎表述，并建议咨询专业人士
- 每条视频展示文章来源和“仅供教育参考”提示
