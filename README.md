# 图片抓取与 CLIP 筛选工具

这是一个 Windows 本地图片抓取工具。网页控制台可以：

- 查看并手动选择 `comprehensive_63_metrics` 中的 63 项预设指标；
- 随机抽取一个预设指标，并调用 Mistral Ministral 14B 改写 high/low 图片搜索词；
- 输入自己的图片搜索话题；
- 调整 CLIP 筛选阈值、每个级别目标图片数和输出目录；
- 查看抓取任务状态和实时日志。

网页服务只绑定到本机 `127.0.0.1`，不对局域网或公网开放。Ministral 14B 通过 Mistral API 远程调用，不会下载模型权重到本机。CLIP 模型在首次筛选图片时会从 Hugging Face 下载并在本机运行。

## 系统要求

- Windows 10/11
- Python 3.10 或更新版本（建议 Python 3.11）
- 已安装 Google Chrome
- 可访问 Hugging Face、Bing 图片搜索和图片来源网站的网络连接
- 磁盘空间：Python、PyTorch 和 Transformers 依赖占用较大；首次运行还会下载 CLIP 模型

## 配置 Python 环境

在 PowerShell 中进入项目目录：

```powershell
cd C:\Users\sunyu\Desktop\AI_Video_generator
```

创建虚拟环境并安装抓取功能依赖：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-scraper.txt
```

如果电脑没有 Python 3.11，可将 `py -3.11` 换成已安装的 Python 启动器版本，例如 `py -3.12`。不要将 Mistral API Key 写入 Python 文件、README 或提交到 Git。

## 配置 Mistral API Key

只有使用“随机抽取 + Ministral 14B 改写”时需要 Mistral API Key。在网页选择该模式后，粘贴从 Mistral 控制台创建的 API Key，再点击“绑定 API Key”。密钥只保存在运行控制台的本机 Python 进程内存中，随机抓取任务启动时才通过子进程环境变量传入；不会写入项目文件、浏览器存储、URL 或任务日志。关闭控制台服务后密钥会清除，需要重新输入。

绑定密钥的接口仅接受当前本机网页的同源请求；页面上的“清除 API Key”按钮会立即从服务内存中删除它。密钥不会通过 API 回传，页面只显示是否已绑定。请确认 Mistral 账户已开通 API 调用权限和额度，并避免在不可信设备上输入。

手动选择 63 项或使用自定义搜索话题不需要 Mistral API Key。

## 启动网页

在项目目录双击 `启动抓取控制台.bat`，或从 PowerShell 启动：

```powershell
.\.venv\Scripts\python.exe .\抓取控制台.py
```

然后在浏览器打开：

```text
http://127.0.0.1:8765
```

运行期间请保持启动控制台的终端窗口开启。按 `Ctrl+C` 或关闭窗口即可停止网页服务。启动器 BAT 不会自动安装依赖；首次运行前仍需完成上面的 Python 环境配置。

## 使用网页

### 手动选择预设指标

1. 选择“手动选择 63 项指标”。
2. 可按名称搜索指标，选择一项或多项。
3. 设置 CLIP 严格度、每个 high/low 级别目标图片数和保存目录。
4. 点击“开始抓取”。

每个指标在脚本中定义有 high 和 low 两种搜索级别；网页上的目标图片数分别应用到每个级别。

### 随机抽取并由 Mistral 改写

1. 选择“随机抽 1 项 + Ministral 14B 改写”。
2. 输入 Mistral API Key 并点击“绑定 API Key”，确认页面显示已绑定。
3. 设置筛选和保存选项，然后开始抓取。

每次启动任务时，程序从全部 63 项中随机选一项，并调用 `ministral-14b-2512` 分别改写该指标的 high/low 搜索词。改写结果会显示在任务日志中。如果 API Key、模型服务或账户额度有问题，任务会报告错误并停止，不会静默切换回原搜索词。

### 自定义搜索话题

选择“自定义搜索话题”，输入图片搜索短语，例如：

```text
adult male fashion model portrait
```

自定义话题会直接作为 Bing 图片搜索词，不需要 Mistral Token。

## CLIP 严格度说明

阈值范围为 `0.35` 到 `0.95`。数值越高，CLIP 越倾向于拒绝图片，可能导致通过筛选的图片较少。CLIP 当前使用通用的真人面部/照片描述进行图文相似度判断；它不是精确的人脸检测器，也不能准确测量或验证外貌指标。请将筛选结果视为自动化候选筛选，而非专业判断。

## 输出位置

网页中的“图片保存根目录”就是分类文件夹的父目录。默认值是项目根目录下的 `抓取结果` 文件夹；填写相对路径时也以项目目录为基准。图片会按以下结构保存：

```text
AI_Video_generator/
└── 抓取结果/
    └── <指标或话题>/
        ├── high/
        └── low/
```

自定义其他保存目录时，目录结构为：

```text
<图片保存根目录>/
└── <指标或话题>/
    ├── high/
    └── low/
```

自定义话题只有一个 `search/` 级别。若该级别已存在足够数量的图片，脚本会跳过已达标的级别；若想重新收集，请在网页选择新的输出目录，或自行备份后清理对应的结果目录。

## 图片管理页面

网页顶部提供“图片管理”页面，可以查看项目中的 JPG、JPEG、PNG 和 WEBP 图片，单独删除图片，或删除包含图片的整个文件夹。删除前会弹出确认；文件夹删除会移除其中所有内容。`.git`、虚拟环境、模型目录和 `music` 等运行目录会被排除或保护；抓取任务运行期间不允许删除。删除操作不可撤销，请先确认目标路径。

## 命令行（可选）

列出内置的 63 项指标：

```powershell
.\.venv\Scripts\python.exe .\自动抓取脚本.py --list-metrics
```

随机选一项并使用 Mistral 改写：

```powershell
.\.venv\Scripts\python.exe .\自动抓取脚本.py --random-mistral --clip-threshold 0.60 --target-count 20 --output-dir "C:\Users\sunyu\Desktop\image_results"
```

选择某项或自定义话题：

```powershell
.\.venv\Scripts\python.exe .\自动抓取脚本.py --metric "颧骨高度" --clip-threshold 0.70 --target-count 10 --output-dir "C:\Users\sunyu\Desktop\image_results"
.\.venv\Scripts\python.exe .\自动抓取脚本.py --custom-topic "adult male fashion model portrait" --clip-threshold 0.60 --target-count 10 --output-dir "C:\Users\sunyu\Desktop\image_results"
```

## 常见问题

- **页面无法打开**：确认控制台终端仍在运行，并访问 `http://127.0.0.1:8765`。
- **Chrome/ChromeDriver 启动失败**：确认 Google Chrome 已安装；首次启动时网络可能需要访问 ChromeDriver 下载源。
- **CLIP 载入或筛选失败**：确认依赖已安装且可访问 Hugging Face。第一次载入会下载模型；模型加载错误会写入抓取日志。
- **Mistral API 认证或调用错误**：确认网页显示 API Key 已绑定、密钥有效，并且 Mistral 账户已开通 API 权限和额度。
- **筛选后图片不足**：尝试降低 CLIP 阈值、降低目标数量，或调整搜索词。搜索结果是否充足取决于搜索服务和来源。

## 图片使用与隐私

请遵守搜索引擎、图片来源网站的使用条款，并在使用或再发布图片前核实授权、版权和肖像权。不要将抓取的私人、敏感或未经许可的个人照片用于公开发布。网页只监听本机，但图片搜索和 Mistral API 请求会访问第三方服务；Mistral 会收到所选指标名称和对应搜索词，不会收到 API Key 或其他本地文件。

## Git 忽略规则

根目录 `.gitignore` 会忽略 Python 字节码、虚拟环境、缓存、密钥文件和常见抓取输出。Git 忽略规则只对尚未跟踪的文件生效；如果 `.venv` 或 `.pyc` 文件以前已经提交过，它们仍处于 Git 跟踪状态。不要直接清空仓库或删除其他人的改动；需要从 Git 跟踪中移除这些旧文件时，请先确认并单独处理。
