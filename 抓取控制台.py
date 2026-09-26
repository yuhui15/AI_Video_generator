"""Local web interface for configuring and running the image crawler."""

from __future__ import annotations

import ast
import html
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from xiaohongshu_publisher.copywriter import generate_copywriting
from xiaohongshu_publisher.image_loader import build_post_images
from xiaohongshu_publisher.publisher import open_filled_draft


ROOT = Path(__file__).resolve().parent
SCRAPER = ROOT / "自动抓取脚本.py"
DEFAULT_OUTPUT = ROOT
MAX_REQUEST_BYTES = 64 * 1024
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PROTECTED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "envs",
    "__pycache__",
    "models",
    "music",
    ".vscode",
    ".idea",
    "node_modules",
    "xiaohongshu_publisher",
}
job_lock = threading.Lock()
job: dict[str, Any] = {
    "status": "idle",
    "logs": [],
    "returncode": None,
    "error": None,
}
mistral_api_key: str | None = None
publisher_lock = threading.Lock()
publisher_state: dict[str, str] = {"status": "idle", "message": ""}
publisher_draft: dict[str, Any] | None = None
publisher_driver: Any = None


def load_metric_names() -> list[str]:
    tree = ast.parse(SCRAPER.read_text(encoding="utf-8"), filename=str(SCRAPER))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "comprehensive_63_metrics"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict) or not all(isinstance(name, str) for name in value):
                break
            return list(value)
    raise RuntimeError("无法从自动抓取脚本读取 comprehensive_63_metrics 指标列表。")


METRIC_NAMES = load_metric_names()


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>图片抓取控制台</title>
  <style>
    :root { color-scheme: light; --bg:#f1f2f3; --panel:#fff; --line:#d7dade; --muted:#687078; --text:#171a1d; --accent:#26618a; --blue:#17699b; --nav:#14171b; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:15px/1.65 "Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif; }
    .topbar { min-height:76px; padding:0 28px; background:rgba(18,21,27,.96); border-bottom:1px solid #30343a; }
    .topbar-inner { max-width:1200px; height:76px; margin:auto; display:flex; align-items:center; justify-content:flex-end; }
    .brand { display:flex; align-items:center; gap:12px; min-height:58px; padding:5px 0 5px 14px; color:#f1f3f4; text-decoration:none; border-left:1px solid #555b62; }
    .brand img { display:block; width:48px; height:44px; object-fit:contain; filter:brightness(0) invert(1); }
    .brand span { font-size:13px; letter-spacing:.12em; white-space:nowrap; }
    main { max-width:1040px; margin:0 auto; padding:64px 24px 80px; }
    .hero { display:grid; grid-template-columns:1.15fr .85fr; gap:42px; align-items:center; margin:0 0 38px; padding:8px 0 42px; border-bottom:1px solid #202326; }
    .eyebrow { margin:0 0 14px; color:#66717a; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }
    h1 { margin:0; font-family:"Noto Serif SC","Songti SC","SimSun",serif; font-size:clamp(34px,5vw,56px); font-weight:500; line-height:1.25; letter-spacing:.035em; }
    .hero-copy { max-width:360px; color:#666e75; font-size:15px; }
    .hero-copy p { margin:7px 0; }
    .badge { display:inline-flex; align-items:center; gap:8px; margin-top:12px; color:#53636e; font-size:12px; letter-spacing:.04em; }
    .badge::before { width:7px; height:7px; border-radius:50%; background:#4c997c; content:""; }
    h2 { margin:0 0 16px; font-family:"Noto Serif SC","Songti SC","SimSun",serif; font-size:21px; font-weight:600; letter-spacing:.025em; }
    p { margin:6px 0; color:var(--muted); }
    .panel { margin:20px 0; padding:26px 28px; border:1px solid var(--line); border-radius:3px; background:var(--panel); box-shadow:0 8px 28px rgba(23,31,38,.035); }
    .mode { display:flex; flex-wrap:wrap; gap:8px; padding-bottom:18px; border-bottom:1px solid #e2e4e5; }
    .mode label,.toolbar button { border:1px solid #d7dade; border-radius:3px; padding:9px 13px; background:#fff; color:#30373d; cursor:pointer; transition:background .16s,border-color .16s,color .16s; }
    .mode label:has(input:checked) { border-color:#1d5c83; background:#edf4f8; color:#174d6e; }
    input,select,button { font:inherit; color:var(--text); }
    input[type="text"],input[type="number"] { width:100%; padding:11px 12px; border:1px solid #cfd4d8; border-radius:2px; background:#fff; }
    select,textarea { width:100%; padding:11px 12px; border:1px solid #cfd4d8; border-radius:2px; background:#fff; font:inherit; }
    textarea { min-height:100px; resize:vertical; }
    input::placeholder { color:#92999f; }
    input:focus,button:focus-visible { outline:2px solid #78a9c5; outline-offset:2px; }
    .field { margin:20px 0 8px; }
    .field>label,.field>legend { display:block; margin-bottom:8px; color:#24292d; font-weight:650; }
    .help { color:var(--muted); font-size:13px; }
    .toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:12px 0; }
    .toolbar input { flex:1; min-width:180px; }
    .toolbar button { padding:7px 11px; color:#245b7c; }
    .toolbar button:hover,.mode label:hover { border-color:#7396aa; background:#f2f6f8; }
    #metrics { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:4px 8px; max-height:280px; overflow:auto; padding:14px; border:1px solid #d9dddf; border-radius:2px; background:#fafbfb; }
    .metric { display:flex; gap:8px; align-items:flex-start; padding:6px 5px; color:#394149; font-size:13px; cursor:pointer; }
    input[type="checkbox"],input[type="radio"] { accent-color:#22658d; }
    input[type="checkbox"] { margin-top:5px; }
    .range-row { display:flex; gap:14px; align-items:center; }
    input[type="range"] { flex:1; accent-color:#286b92; }
    output { min-width:100px; text-align:right; color:#245b7c; font-weight:700; }
    .grid { display:grid; grid-template-columns:1fr 2fr; gap:20px; }
    .submit { width:100%; min-height:50px; padding:13px 18px; border:1px solid #164e75; border-radius:3px; background:#174f77; color:#fff; font-weight:700; letter-spacing:.06em; cursor:pointer; transition:background .16s; }
    .submit:hover:not(:disabled) { background:#103f63; }
    .submit:disabled { opacity:.55; cursor:wait; }
    #status { margin:0 0 10px; color:#245b7c; font-weight:700; }
    #logs { min-height:140px; max-height:340px; overflow:auto; padding:16px; white-space:pre-wrap; overflow-wrap:anywhere; border:1px solid #d6dadd; border-radius:2px; background:#f8f9f9; color:#333b40; font:12px/1.7 ui-monospace,Consolas,monospace; }
    .warning { padding:12px 14px; border-left:2px solid #a88751; background:#f8f6f1; color:#615744; font-size:13px; }
    .nav-actions { display:flex; gap:10px; margin:24px 0; }
    .nav-actions button,.item-action { border:1px solid #cbd2d7; border-radius:3px; padding:9px 13px; background:#fff; color:#245b7c; cursor:pointer; }
    .nav-actions button[aria-current="page"] { background:#174f77; border-color:#174f77; color:#fff; }
    .token-controls { display:grid; grid-template-columns:minmax(0,1fr) auto auto; gap:8px; align-items:center; margin:12px 0 6px; }
    .token-controls input { min-width:0; padding:11px 12px; border:1px solid #cfd4d8; border-radius:2px; background:#fff; }
    .token-controls button { border:1px solid #cbd2d7; border-radius:3px; padding:10px 13px; background:#fff; color:#245b7c; cursor:pointer; }
    .token-controls button:hover { background:#f2f6f8; }
    #token-status { min-height:22px; margin:5px 0 0; font-size:13px; }
    #token-status[data-configured="true"] { color:#28734f; }
    #token-status[data-configured="false"] { color:#805d28; }
    .file-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:14px 0; }
    .file-toolbar button,.breadcrumb button { border:1px solid #cbd2d7; border-radius:3px; padding:8px 12px; background:#fff; color:#245b7c; cursor:pointer; }
    .file-toolbar button:disabled { opacity:.5; cursor:not-allowed; }
    .breadcrumb { display:flex; flex-wrap:wrap; align-items:center; gap:6px; min-height:40px; padding:8px 10px; border:1px solid #d9dddf; background:#f8fafb; }
    .breadcrumb button { border:0; padding:3px 6px; background:transparent; }
    .breadcrumb button:hover { background:#eaf1f5; }
    .breadcrumb-separator { color:#8a9298; }
    #library-list { display:grid; grid-template-columns:repeat(auto-fill,minmax(155px,1fr)); gap:12px; margin-top:14px; }
    .library-card { position:relative; display:flex; min-width:0; flex-direction:column; gap:7px; padding:9px; border:1px solid #d9dddf; border-radius:3px; background:#fafbfb; }
    .library-card:hover { border-color:#91aaba; background:#f4f8fa; }
    .library-open { display:flex; min-width:0; flex:1; flex-direction:column; align-items:stretch; gap:7px; padding:0; border:0; background:transparent; color:#28343b; text-align:left; cursor:pointer; }
    .library-open:focus-visible { outline:2px solid #78a9c5; outline-offset:2px; }
    .library-preview { display:grid; width:100%; height:116px; place-items:center; overflow:hidden; border:1px solid #e1e5e7; background:linear-gradient(135deg,#f0f3f4,#e7ecef); color:#4e6573; font-size:34px; }
    .library-preview img { width:100%; height:100%; object-fit:cover; }
    .library-name { width:100%; overflow:hidden; color:#28343b; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
    .library-meta { color:#78828a; font-size:11px; }
    .library-card .item-action { align-self:flex-end; padding:5px 9px; font-size:12px; }
    .item-action.danger { border-color:#b44b42; color:#9d2f27; }
    .item-action:disabled { opacity:.55; cursor:wait; }
    #image-preview { width:min(92vw,1000px); max-width:none; max-height:90vh; padding:16px; border:1px solid #ccd3d8; border-radius:4px; background:#fff; box-shadow:0 18px 70px rgba(0,0,0,.35); }
    #image-preview::backdrop { background:rgba(12,17,21,.72); }
    #preview-image { display:block; max-width:100%; max-height:calc(90vh - 90px); margin:0 auto; object-fit:contain; }
    .preview-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px; }
    #preview-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    #publisher-images { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:10px; margin:16px 0; }
    .publisher-image { min-width:0; padding:7px; border:1px solid #d9dddf; background:#fafbfb; }
    .publisher-image img { width:100%; height:120px; object-fit:cover; }
    .publisher-image span { display:block; overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
    #publisher-state { min-height:24px; color:#245b7c; font-weight:650; }
    .publisher-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
    [hidden] { display:none!important; }
    @media(max-width:700px) { .topbar { padding:0 18px; } main { padding:42px 18px 56px; } .hero { grid-template-columns:1fr; gap:12px; padding-bottom:28px; } .hero-copy { max-width:none; } .grid { grid-template-columns:1fr; gap:0; } .panel { padding:20px 18px; } .brand { gap:8px; } .brand img { width:42px; height:39px; } }
    @media(max-width:560px) { .token-controls { grid-template-columns:1fr 1fr; } .token-controls input { grid-column:1/-1; } }
  </style>
</head>
<body>
<nav class="topbar" aria-label="品牌">
  <div class="topbar-inner">
    <a class="brand" href="https://www.yanzumeixue.com/" target="_blank" rel="noopener noreferrer" aria-label="彦祖美学官网">
      <img src="https://www.yanzumeixue.com/images/yanzu-meixue.svg" alt="彦祖美学 Logo">
      <span>彦祖美学</span>
    </a>
  </div>
</nav>
<main>
  <header class="hero">
    <div>
      <p class="eyebrow">IMAGE RESEARCH / LOCAL TOOL</p>
      <h1>图片抓取控制台</h1>
    </div>
    <div class="hero-copy">
      <p>从预设指标或自定义话题出发，整理可供研究的图片样本。</p>
      <p>设定筛选标准，让每一次采集都有清晰的方向。</p>
      <span class="badge">仅监听本机 · 不会公开到网络</span>
    </div>
  </header>
    <nav class="nav-actions" aria-label="页面">
      <button type="button" id="show-crawler" aria-current="page">抓取控制台</button>
      <button type="button" id="show-manager">图片管理</button>
      <button type="button" id="show-publisher">小红书发布</button>
    </nav>
    <section id="publisher-page" hidden>
      <section class="panel">
        <h2>小红书图文准备与发布</h2>
        <p>从本地图片目录抽取素材，用 Ministral 14B 生成文案并预览；图片最后自动附加彦祖美学推广图。</p>
        <div class="warning">生成的草稿不会自动公开发布。打开创作者平台后，请检查图片、标题和正文，并由你手动点击小红书页面上的“发布”。请确保你有权使用所选图片。</div>
        <div class="field">
          <label for="publisher-mode">内容类别</label>
          <select id="publisher-mode">
            <option value="comparison">63 项美学指标：High / Low 对比</option>
            <option value="topic">话题文件夹：自定义文案</option>
          </select>
        </div>
        <div class="field">
          <label for="publisher-folder">素材文件夹</label>
          <select id="publisher-folder"></select>
          <p class="help" id="publisher-folder-help"></p>
        </div>
        <div class="field">
          <label for="publisher-count">抽取数量</label>
          <input id="publisher-count" type="number" min="1" max="8" value="3">
          <p class="help" id="publisher-count-help">High 和 Low 各抽取此数量；推广图不计入数量。</p>
        </div>
        <div class="field">
          <label for="publisher-prompt">创作者补充 Prompt</label>
          <textarea id="publisher-prompt" maxlength="2000" placeholder="补充语气、重点或内容结构要求"></textarea>
        </div>
        <button type="button" class="submit" id="prepare-publisher">随机抽图并生成文案</button>
        <p id="publisher-state" role="status" aria-live="polite">先选择素材文件夹，再生成草稿。</p>
      </section>
      <section class="panel" id="publisher-preview-panel" hidden>
        <h2>发布预览</h2>
        <p id="publisher-image-summary"></p>
        <div id="publisher-images"></div>
        <div class="field">
          <label for="publisher-title">标题（最多 20 字）</label>
          <input id="publisher-title" type="text" maxlength="20">
        </div>
        <div class="field">
          <label for="publisher-content">正文（最多 1000 字）</label>
          <textarea id="publisher-content" maxlength="1000"></textarea>
        </div>
        <div class="publisher-actions">
          <button type="button" class="item-action" id="regenerate-publisher">重新抽图并生成文案</button>
          <button type="button" class="submit" id="open-publisher">打开小红书编辑页并填入草稿</button>
          <button type="button" class="item-action" id="close-publisher" hidden>关闭发布浏览器</button>
        </div>
      </section>
    </section>
    <section id="manager-page" hidden>
      <section class="panel">
        <h2>图片与文件夹管理</h2>
        <p>管理项目目录中的 JPG、JPEG、PNG、WEBP 图片。删除文件夹会永久删除其中所有内容，请仔细确认。</p>
        <p class="help">不会列出或删除 .git、虚拟环境、models、music 等项目运行目录。</p>
        <div class="toolbar">
          <button type="button" id="refresh-library">刷新列表</button>
          <span class="help" id="library-status" role="status"></span>
        </div>
        <div class="file-toolbar">
          <button type="button" id="library-back" disabled>返回上一级</button>
          <button type="button" id="library-root">项目根目录</button>
        </div>
        <nav id="library-breadcrumb" class="breadcrumb" aria-label="当前文件夹路径"></nav>
        <div id="library-list" aria-live="polite"></div>
      </section>
    </section>
    <dialog id="image-preview">
      <div class="preview-toolbar">
        <strong id="preview-name"></strong>
        <button type="button" class="item-action" id="close-preview">关闭</button>
      </div>
      <img id="preview-image" alt="图片预览">
      <div class="preview-toolbar">
        <span class="help" id="preview-path"></span>
        <button type="button" class="item-action danger" id="preview-delete">删除照片</button>
      </div>
    </dialog>
    <section id="crawler-page">
    <form id="crawl-form">
    <section class="panel">
      <h2>1. 选择抓取内容</h2>
      <div class="mode">
        <label><input type="radio" name="mode" value="metrics" checked> 选择一个指标 + Ministral 14B 改写</label>
        <label><input type="radio" name="mode" value="custom"> 自定义搜索话题</label>
      </div>
      <div id="metric-section" class="field">
        <div class="toolbar">
          <input id="metric-filter" type="text" placeholder="搜索指标名称">
          <span class="help" id="selected-count">请选择一个指标</span>
        </div>
        <div id="metrics" aria-label="63 项指标列表"></div>
        <p class="help" id="metric-help">选定指标后点击“改写搜索词”，核对 high / low 搜索词，再开始抓取。</p>
        <p class="help">保存文件夹始终使用改写前选中的指标名称；改写后的搜索词只用于搜索，不会改变文件夹名。</p>
        <p class="help">图片搜索限制在 looksmax.org，使用 Bing 图片搜索站内结果。</p>
        <p class="help">模型：ministral-14b-2512（通过 Mistral API 调用）</p>
        <label for="mistral-api-key">Mistral API Key</label>
        <div class="token-controls">
          <input id="mistral-api-key" type="password" autocomplete="new-password" spellcheck="false" placeholder="粘贴 Mistral API Key" aria-describedby="token-help token-status">
          <button type="button" id="bind-token">绑定 API Key</button>
          <button type="button" id="clear-token">清除 API Key</button>
        </div>
        <p class="help" id="token-help">API Key 只保存在本机服务内存中，并在抓取时传给子进程；不会写入文件、浏览器存储或任务日志。关闭服务后需重新输入。</p>
        <p id="token-status" role="status" aria-live="polite" data-configured="false">正在检查 API Key 状态…</p>
        <button type="button" id="rewrite-query">改写搜索词</button>
        <div id="rewritten-queries" class="field" aria-live="polite" hidden>
          <p><strong>High 搜索词</strong></p>
          <pre id="rewritten-high"></pre>
          <p><strong>Low 搜索词</strong></p>
          <pre id="rewritten-low"></pre>
        </div>
      </div>
      <div id="custom-section" class="field" hidden>
        <label for="custom-topic">抓取标题 / 搜索话题</label>
        <input id="custom-topic" type="text" maxlength="240" placeholder="例如：adult male fashion model portrait">
        <p class="help">该文本将直接作为 Bing 图片搜索词，同时用于创建结果子目录。</p>
      </div>
    </section>
    <section class="panel">
      <h2>2. 设置筛选和保存选项</h2>
      <div class="field">
        <label for="threshold">CLIP 筛选严格度</label>
        <div class="range-row">
          <span class="help">宽松</span>
          <input id="threshold" type="range" min="0.35" max="0.95" step="0.01" value="0.60">
          <span class="help">严格</span>
          <output id="threshold-value" for="threshold">0.60 · 标准</output>
        </div>
        <p class="help">值越高，CLIP 对“清晰、单人、真人面部、眼睛可见”的要求越高，合格图片可能更少。</p>
      </div>
      <div class="grid">
        <div class="field">
          <label for="target-count">每个级别目标图片数</label>
          <input id="target-count" type="number" min="1" max="1000" value="20">
        </div>
        <div class="field">
          <label for="output-dir">图片保存根目录</label>
          <input id="output-dir" type="text" value="__DEFAULT_OUTPUT__">
          <p class="help">默认直接保存在项目根目录下，以原始指标名创建文件夹（例如“面部长宽比”）；改写词不会改变文件夹名。相对路径以项目根目录为基准。</p>
        </div>
      </div>
      <div class="warning">请确认抓取和使用图片符合网站条款、版权和肖像权要求。CLIP 是图文相似度筛选，不是准确的人脸或美学测量工具。</div>
    </section>
    <button class="submit" id="start" type="submit">开始抓取</button>
  </form>
  <section class="panel" aria-live="polite">
    <h2>任务状态</h2>
    <div id="status">空闲</div>
    <pre id="logs">尚未启动抓取任务。</pre>
  </section>
  </section>
</main>
<script>
const metricsRoot = document.getElementById("metrics");
const form = document.getElementById("crawl-form");
const startButton = document.getElementById("start");
const statusElement = document.getElementById("status");
const logsElement = document.getElementById("logs");
const crawlerPage = document.getElementById("crawler-page");
const managerPage = document.getElementById("manager-page");
const publisherPage = document.getElementById("publisher-page");
const libraryList = document.getElementById("library-list");
const libraryStatus = document.getElementById("library-status");
const libraryBreadcrumb = document.getElementById("library-breadcrumb");
const libraryBack = document.getElementById("library-back");
const previewDialog = document.getElementById("image-preview");
const previewImage = document.getElementById("preview-image");
let currentLibraryPath = "";
let previewedImagePath = "";
const metricFilter = document.getElementById("metric-filter");
const tokenInput = document.getElementById("mistral-api-key");
const tokenStatus = document.getElementById("token-status");
let timer = null;
let publisherTimer = null;
let rewrittenMetric = null;
let rewrittenQueries = null;

function updateMode() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const manual = mode === "metrics";
  const metricSection = document.getElementById("metric-section");
  metricSection.hidden = mode === "custom";
  metricsRoot.querySelectorAll("input").forEach(item => { item.disabled = !manual; });
  document.getElementById("metric-filter").disabled = !manual;
  document.getElementById("custom-section").hidden = mode !== "custom";
}
function updateCount() {
  const selected = metricsRoot.querySelector("input:checked");
  document.getElementById("selected-count").textContent = selected
    ? `已选：${selected.value}`
    : "请选择一个指标";
  if (rewrittenMetric !== (selected && selected.value)) {
    rewrittenMetric = null;
    rewrittenQueries = null;
    document.getElementById("rewritten-queries").hidden = true;
  }
}
function updateThreshold() {
  const value = Number(document.getElementById("threshold").value);
  const level = value < 0.55 ? "宽松" : value < 0.76 ? "标准" : "严格";
  document.getElementById("threshold-value").textContent = `${value.toFixed(2)} · ${level}`;
}
function filterMetrics() {
  const query = metricFilter.value.trim().toLocaleLowerCase();
  for (const item of metricsRoot.children) {
    item.hidden = !item.dataset.name.toLocaleLowerCase().includes(query);
  }
}
async function loadMetrics() {
  const response = await fetch("/api/metrics");
  if (!response.ok) throw new Error("无法读取指标列表");
  const names = await response.json();
  for (const name of names) {
    const label = document.createElement("label");
    label.className = "metric";
    label.dataset.name = name;
    const checkbox = document.createElement("input");
    checkbox.type = "radio";
    checkbox.name = "metric";
    checkbox.value = name;
    checkbox.addEventListener("change", updateCount);
    const text = document.createElement("span");
    text.textContent = name;
    label.append(checkbox, text);
    metricsRoot.append(label);
  }
  updateMode();
  updateCount();
}
async function refreshTokenStatus() {
  try {
    const response = await fetch("/api/mistral-key/status", {cache:"no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法读取 API Key 状态");
    tokenStatus.dataset.configured = String(data.configured);
    tokenStatus.textContent = data.configured
      ? "Mistral API Key 已绑定到本机服务（只显示状态，不回显密钥）。"
      : "尚未绑定 Mistral API Key；改写搜索词前请先绑定。";
  } catch (error) {
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = `API Key 状态读取失败：${error.message}`;
  }
}
document.getElementById("bind-token").addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) {
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = "请先输入 Mistral API Key。";
    tokenInput.focus();
    return;
  }
  const button = document.getElementById("bind-token");
  button.disabled = true;
  try {
    const response = await fetch("/api/mistral-key", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      cache:"no-store",
      body:JSON.stringify({api_key:token})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "API Key 绑定失败");
    tokenInput.value = "";
    tokenStatus.dataset.configured = "true";
    tokenStatus.textContent = "Mistral API Key 已绑定到本机服务内存；页面不会保存或回显它。";
  } catch (error) {
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = `API Key 绑定失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});
document.getElementById("clear-token").addEventListener("click", async () => {
  const button = document.getElementById("clear-token");
  button.disabled = true;
  try {
    const response = await fetch("/api/mistral-key/clear", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      cache:"no-store",
      body:"{}"
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "API Key 清除失败");
    tokenInput.value = "";
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = "Mistral API Key 已从本机服务内存中清除。";
  } catch (error) {
    tokenStatus.textContent = `API Key 清除失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});
document.querySelectorAll('input[name="mode"]').forEach(item => item.addEventListener("change", updateMode));
document.getElementById("threshold").addEventListener("input", updateThreshold);
metricFilter.addEventListener("input", filterMetrics);
document.getElementById("rewrite-query").addEventListener("click", async () => {
  const selected = metricsRoot.querySelector("input:checked");
  if (!selected) {
    tokenStatus.textContent = "请先选择一个指标。";
    return;
  }
  const button = document.getElementById("rewrite-query");
  button.disabled = true;
  tokenStatus.textContent = "正在调用 Ministral 14B 改写 high / low 搜索词…";
  try {
    const response = await fetch("/api/rewrite", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({metric:selected.value})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "搜索词改写失败");
    rewrittenMetric = selected.value;
    rewrittenQueries = data.queries;
    document.getElementById("rewritten-high").textContent = rewrittenQueries.high;
    document.getElementById("rewritten-low").textContent = rewrittenQueries.low;
    document.getElementById("rewritten-queries").hidden = false;
    tokenStatus.textContent = `已用 ${data.model} 改写。搜索限定于 looksmax.org；请确认搜索词后开始抓取。`;
  } catch (error) {
    rewrittenMetric = null;
    rewrittenQueries = null;
    document.getElementById("rewritten-queries").hidden = true;
    tokenStatus.textContent = `改写失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});
async function pollStatus() {
  const response = await fetch("/api/status");
  const data = await response.json();
  const labels = {idle:"空闲", starting:"启动中", running:"抓取中", completed:"已完成", failed:"失败"};
  statusElement.textContent = labels[data.status] || data.status;
  if (data.error) statusElement.textContent += `：${data.error}`;
  logsElement.textContent = data.logs || "等待抓取日志…";
  logsElement.scrollTop = logsElement.scrollHeight;
  startButton.disabled = data.status === "starting" || data.status === "running";
  if (startButton.disabled) timer = setTimeout(pollStatus, 1000);
}
document.getElementById("show-crawler").addEventListener("click", event => {
  crawlerPage.hidden = false;
  managerPage.hidden = true;
  publisherPage.hidden = true;
  event.currentTarget.setAttribute("aria-current", "page");
  document.getElementById("show-manager").removeAttribute("aria-current");
  document.getElementById("show-publisher").removeAttribute("aria-current");
});
document.getElementById("show-manager").addEventListener("click", event => {
  crawlerPage.hidden = true;
  managerPage.hidden = false;
  publisherPage.hidden = true;
  event.currentTarget.setAttribute("aria-current", "page");
  document.getElementById("show-crawler").removeAttribute("aria-current");
  document.getElementById("show-publisher").removeAttribute("aria-current");
  loadLibrary();
});
document.getElementById("show-publisher").addEventListener("click", event => {
  crawlerPage.hidden = true;
  managerPage.hidden = true;
  publisherPage.hidden = false;
  event.currentTarget.setAttribute("aria-current", "page");
  document.getElementById("show-crawler").removeAttribute("aria-current");
  document.getElementById("show-manager").removeAttribute("aria-current");
  loadPublisherFolders();
  pollPublisherStatus();
});
function renderBreadcrumb(path) {
  libraryBreadcrumb.replaceChildren();
  const rootButton = document.createElement("button");
  rootButton.type = "button";
  rootButton.textContent = "项目根目录";
  rootButton.addEventListener("click", () => loadLibrary(""));
  libraryBreadcrumb.append(rootButton);
  let accumulated = "";
  for (const segment of path.split("/").filter(Boolean)) {
    const separator = document.createElement("span");
    separator.className = "breadcrumb-separator";
    separator.textContent = "›";
    libraryBreadcrumb.append(separator);
    accumulated = accumulated ? `${accumulated}/${segment}` : segment;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = segment;
    const targetPath = accumulated;
    button.addEventListener("click", () => loadLibrary(targetPath));
    libraryBreadcrumb.append(button);
  }
  libraryBack.disabled = !path;
}
function makeLibraryCard(item, kind) {
  const card = document.createElement("article");
  card.className = "library-card";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "library-open";
  const preview = document.createElement("span");
  preview.className = "library-preview";
  if (kind === "folder") {
    preview.textContent = "📁";
  } else {
    const image = document.createElement("img");
    image.src = `/api/manage/image?path=${encodeURIComponent(item.path)}`;
    image.alt = "";
    image.loading = "lazy";
    image.addEventListener("error", () => { preview.textContent = "无法预览"; });
    preview.append(image);
  }
  const name = document.createElement("span");
  name.className = "library-name";
  name.textContent = item.name;
  open.append(preview, name);
  if (kind === "folder") {
    const meta = document.createElement("span");
    meta.className = "library-meta";
    meta.textContent = item.image_count ? `${item.image_count} 张图片` : "文件夹";
    open.append(meta);
    open.addEventListener("click", () => loadLibrary(item.path));
  } else {
    const meta = document.createElement("span");
    meta.className = "library-meta";
    meta.textContent = `${(item.size / 1024).toFixed(1)} KB`;
    open.append(meta);
    open.addEventListener("click", () => showImagePreview(item));
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "item-action danger";
  remove.textContent = kind === "folder" ? "删除文件夹" : "删除照片";
  remove.addEventListener("click", () => deleteLibraryItem(item.path, kind));
  card.append(open, remove);
  return card;
}
function showImagePreview(item) {
  previewedImagePath = item.path;
  previewImage.src = `/api/manage/image?path=${encodeURIComponent(item.path)}`;
  document.getElementById("preview-name").textContent = item.name;
  document.getElementById("preview-path").textContent = item.path;
  previewDialog.showModal();
}
async function loadLibrary(path = currentLibraryPath) {
  libraryStatus.textContent = "正在读取…";
  libraryList.replaceChildren();
  try {
    const response = await fetch(`/api/manage/list?path=${encodeURIComponent(path)}`, {cache:"no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "读取失败");
    currentLibraryPath = data.path;
    renderBreadcrumb(currentLibraryPath);
    for (const folder of data.folders) libraryList.append(makeLibraryCard(folder, "folder"));
    for (const image of data.images) libraryList.append(makeLibraryCard(image, "image"));
    libraryStatus.textContent = `${data.folders.length} 个文件夹，${data.images.length} 张照片`;
    if (data.folders.length === 0 && data.images.length === 0) {
      libraryStatus.textContent += " · 此文件夹为空";
    }
  } catch (error) {
    libraryStatus.textContent = `读取失败：${error.message}`;
  }
}
async function deleteLibraryItem(path, kind) {
  const target = kind === "folder" ? "整个文件夹及其全部内容" : "这张图片";
  if (!confirm(`确定永久删除${target}吗？\n\n${path}`)) return;
  try {
    const response = await fetch("/api/manage/delete", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({path, kind})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "删除失败");
    libraryStatus.textContent = `已删除：${path}`;
    if (previewedImagePath === path) previewDialog.close();
    previewedImagePath = "";
    await loadLibrary(currentLibraryPath);
  } catch (error) {
    libraryStatus.textContent = `删除失败：${error.message}`;
  }
}
libraryBack.addEventListener("click", () => {
  const parts = currentLibraryPath.split("/").filter(Boolean);
  parts.pop();
  loadLibrary(parts.join("/"));
});
document.getElementById("library-root").addEventListener("click", () => loadLibrary(""));
document.getElementById("refresh-library").addEventListener("click", () => loadLibrary(currentLibraryPath));
document.getElementById("close-preview").addEventListener("click", () => {
  previewDialog.close();
  previewedImagePath = "";
});
document.getElementById("preview-delete").addEventListener("click", () => {
  if (previewedImagePath) deleteLibraryItem(previewedImagePath, "image");
});
let publisherFolders = [];
function updatePublisherMode() {
  const comparison = document.getElementById("publisher-mode").value === "comparison";
  const countInput = document.getElementById("publisher-count");
  countInput.max = comparison ? "8" : "17";
  if (Number(countInput.value) > Number(countInput.max)) countInput.value = countInput.max;
  document.getElementById("publisher-count-help").textContent = comparison
    ? "High 和 Low 各抽取此数量；最多 8 张/组。最后会附加推广图。"
    : "从所选话题文件夹及其普通子目录中抽取；最多 17 张。最后会附加推广图。";
  renderPublisherFolderOptions();
}
function renderPublisherFolderOptions() {
  const mode = document.getElementById("publisher-mode").value;
  const select = document.getElementById("publisher-folder");
  const available = publisherFolders.filter(folder => mode === "comparison"
    ? folder.is_metric
    : !folder.is_metric);
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = available.length ? "请选择文件夹" : "没有可用的文件夹";
  select.append(placeholder);
  for (const folder of available) {
    const option = document.createElement("option");
    option.value = folder.path;
    option.textContent = `${folder.name} · ${folder.image_count} 张照片`;
    select.append(option);
  }
  document.getElementById("publisher-folder-help").textContent = mode === "comparison"
    ? "只显示含 high 和 low 两个图片子文件夹的美学指标。"
    : "只显示普通话题文件夹；指标文件夹会从此列表中排除。";
}
async function loadPublisherFolders() {
  const select = document.getElementById("publisher-folder");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.textContent = "正在读取项目图片文件夹…";
  select.append(placeholder);
  try {
    const response = await fetch("/api/publisher/folders", {cache:"no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "读取文件夹失败");
    publisherFolders = data.folders;
    updatePublisherMode();
  } catch (error) {
    document.getElementById("publisher-state").textContent = `读取素材文件夹失败：${error.message}`;
  }
}
function renderPublisherPreview(data) {
  const panel = document.getElementById("publisher-preview-panel");
  const imageList = document.getElementById("publisher-images");
  imageList.replaceChildren();
  for (let index = 0; index < data.images.length; index += 1) {
    const image = data.images[index];
    const card = document.createElement("div");
    card.className = "publisher-image";
    const preview = document.createElement("img");
    preview.src = `/api/publisher/image?index=${index}`;
    preview.alt = image.name;
    const label = document.createElement("span");
    label.textContent = image.name;
    card.append(preview, label);
    imageList.append(card);
  }
  document.getElementById("publisher-image-summary").textContent =
    `${data.images.length - 1} 张抽取图片 + 最后一张彦祖美学推广图`;
  document.getElementById("publisher-title").value = data.copy.title;
  document.getElementById("publisher-content").value = data.copy.content;
  document.getElementById("publisher-state").textContent = "文案和图片已准备好。请审核并可编辑后，再打开发布编辑页。";
  panel.hidden = false;
}
async function preparePublisherDraft() {
  const button = document.getElementById("prepare-publisher");
  const mode = document.getElementById("publisher-mode").value;
  const folder = document.getElementById("publisher-folder").value;
  const count = Number(document.getElementById("publisher-count").value);
  if (!folder) {
    document.getElementById("publisher-state").textContent = "请先选择素材文件夹。";
    return;
  }
  button.disabled = true;
  document.getElementById("publisher-preview-panel").hidden = true;
  document.getElementById("publisher-state").textContent = "正在随机抽图并请求 Ministral 14B 生成文案…";
  try {
    const response = await fetch("/api/publisher/prepare", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        mode,
        folder,
        count,
        prompt:document.getElementById("publisher-prompt").value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法准备发布草稿");
    renderPublisherPreview(data);
  } catch (error) {
    document.getElementById("publisher-state").textContent = `草稿准备失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
}
document.getElementById("publisher-mode").addEventListener("change", updatePublisherMode);
document.getElementById("prepare-publisher").addEventListener("click", preparePublisherDraft);
document.getElementById("regenerate-publisher").addEventListener("click", preparePublisherDraft);
document.getElementById("open-publisher").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/api/publisher/launch", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        title:document.getElementById("publisher-title").value,
        content:document.getElementById("publisher-content").value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法打开小红书编辑页");
    document.getElementById("publisher-state").textContent = data.message;
    pollPublisherStatus();
  } catch (error) {
    document.getElementById("publisher-state").textContent = `打开发布页失败：${error.message}`;
    button.disabled = false;
  }
});
async function pollPublisherStatus() {
  try {
    const response = await fetch("/api/publisher/status", {cache:"no-store"});
    const data = await response.json();
    document.getElementById("publisher-state").textContent = data.message;
    document.getElementById("open-publisher").disabled =
      data.status === "starting" || data.status === "ready" || data.status === "closing";
    document.getElementById("close-publisher").hidden = data.status !== "ready";
    clearTimeout(publisherTimer);
    if (data.status === "starting") publisherTimer = setTimeout(pollPublisherStatus, 1500);
  } catch (error) {
    document.getElementById("publisher-state").textContent = `发布状态读取失败：${error.message}`;
  }
}
document.getElementById("close-publisher").addEventListener("click", async () => {
  try {
    const response = await fetch("/api/publisher/close", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:"{}"
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法关闭浏览器");
    document.getElementById("publisher-state").textContent = data.message;
    await pollPublisherStatus();
  } catch (error) {
    document.getElementById("publisher-state").textContent = `关闭发布浏览器失败：${error.message}`;
  }
});
form.addEventListener("submit", async event => {
  event.preventDefault();
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const selectedMetrics = [...metricsRoot.querySelectorAll("input:checked")].map(item => item.value);
  const payload = {
    mode,
    metrics: selectedMetrics,
    rewritten_queries: rewrittenMetric === selectedMetrics[0] ? rewrittenQueries : null,
    custom_topic: document.getElementById("custom-topic").value.trim(),
    threshold: Number(document.getElementById("threshold").value),
    target_count: Number(document.getElementById("target-count").value),
    output_dir: document.getElementById("output-dir").value.trim()
  };
  if (mode === "metrics" && selectedMetrics.length !== 1) {
    statusElement.textContent = "请选择一个指标。";
    return;
  }
  if (mode === "metrics" && !payload.rewritten_queries) {
    statusElement.textContent = "请先点击“改写搜索词”，查看 high / low 结果后再抓取。";
    return;
  }
  if (mode === "custom" && !payload.custom_topic) {
    statusElement.textContent = "请填写自定义搜索话题。";
    return;
  }
  startButton.disabled = true;
  try {
    const response = await fetch("/api/start", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法启动任务");
    statusElement.textContent = "任务已提交";
    clearTimeout(timer);
    await pollStatus();
  } catch (error) {
    statusElement.textContent = `启动失败：${error.message}`;
    startButton.disabled = false;
  }
});
updateMode();
updateThreshold();
refreshTokenStatus();
loadMetrics().catch(error => { statusElement.textContent = error.message; });
</script>
</body>
</html>
"""


def append_log(message: str) -> None:
    with job_lock:
        job["logs"].append(message.rstrip())
        if len(job["logs"]) > 3000:
            job["logs"] = job["logs"][-3000:]


def list_managed_directory(relative_path: str) -> dict[str, Any]:
    current = ROOT if not relative_path else resolve_managed_path(relative_path)
    if not current.exists() or not current.is_dir() or current.is_symlink():
        raise FileNotFoundError("文件夹不存在或无法访问。")

    folders: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for child in current.iterdir():
        if child.is_symlink():
            continue
        if child.is_dir():
            if child.name.lower() in PROTECTED_DIRS:
                continue
            image_count = count_managed_images(child)
            if not image_count:
                continue
            relative = child.relative_to(ROOT).as_posix()
            folders.append({
                "name": child.name,
                "path": relative,
                "image_count": image_count,
            })
        elif child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS:
            relative = child.relative_to(ROOT).as_posix()
            images.append({
                "name": child.name,
                "path": relative,
                "size": child.stat().st_size,
            })

    return {
        "path": "" if current == ROOT else current.relative_to(ROOT).as_posix(),
        "folders": sorted(folders, key=lambda item: item["name"].casefold()),
        "images": sorted(images, key=lambda item: item["name"].casefold()),
    }


def count_managed_images(path: Path) -> int:
    count = 0
    for current, directories, filenames in os.walk(path, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name.lower() not in PROTECTED_DIRS
            and not (current_path / name).is_symlink()
        ]
        count += sum(
            1 for name in filenames
            if Path(name).suffix.lower() in IMAGE_EXTENSIONS
            and not (current_path / name).is_symlink()
        )
    return count


def resolve_managed_path(relative_path: Any) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("缺少有效的相对路径。")
    supplied = Path(relative_path)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise ValueError("只允许操作项目目录中的相对路径。")
    if any(part.lower() in PROTECTED_DIRS for part in supplied.parts):
        raise ValueError("该路径属于受保护目录，不能通过管理页删除。")
    candidate = ROOT / supplied
    if any((ROOT / Path(*supplied.parts[:index])).is_symlink() for index in range(1, len(supplied.parts) + 1)):
        raise ValueError("不允许通过符号链接操作文件。")
    resolved = candidate.resolve()
    if resolved == ROOT or not resolved.is_relative_to(ROOT):
        raise ValueError("只能操作项目根目录内部的文件或文件夹。")
    return resolved


def directory_contains_images(path: Path) -> bool:
    for current, directories, filenames in os.walk(path, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name.lower() not in PROTECTED_DIRS
            and not (current_path / name).is_symlink()
        ]
        if any(Path(name).suffix.lower() in IMAGE_EXTENSIONS for name in filenames):
            return True
    return False


def directory_is_safe_to_delete(path: Path) -> bool:
    for current, directories, filenames in os.walk(path, followlinks=False):
        current_path = Path(current)
        if any(name.lower() in PROTECTED_DIRS for name in directories):
            return False
        if any((current_path / name).is_symlink() for name in directories + filenames):
            return False
    return True


def delete_managed_item(relative_path: Any, kind: Any) -> None:
    path = resolve_managed_path(relative_path)
    if not path.exists():
        raise FileNotFoundError("目标不存在，可能已被删除。")
    if path.is_symlink():
        raise ValueError("不允许删除符号链接。")
    if kind == "image":
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError("目标不是受支持的图片文件。")
        path.unlink()
        return
    if kind == "folder":
        if not path.is_dir() or not directory_contains_images(path):
            raise ValueError("只能删除包含图片的文件夹。")
        if not directory_is_safe_to_delete(path):
            raise ValueError("文件夹内含受保护目录或符号链接，为避免误删已拒绝操作。")
        shutil.rmtree(path)
        return
    raise ValueError("删除类型必须是 image 或 folder。")


def run_crawler(command: list[str]) -> None:
    with job_lock:
        job["status"] = "running"
    try:
        child_env = os.environ.copy()
        child_env.pop("HF_TOKEN", None)
        child_env.pop("HUGGINGFACEHUB_API_TOKEN", None)
        child_env.pop("MISTRAL_API_KEY", None)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if process.stdout is None:
            raise RuntimeError("无法读取抓取脚本输出。")
        for line in process.stdout:
            append_log(line)
        returncode = process.wait()
        with job_lock:
            job["returncode"] = returncode
            job["status"] = "completed" if returncode == 0 else "failed"
            if returncode != 0:
                job["error"] = f"抓取脚本退出码：{returncode}"
    except OSError as exc:
        with job_lock:
            job["status"] = "failed"
            job["error"] = str(exc)


def run_publisher_browser(
    image_paths: list[Path],
    title: str,
    content: str,
) -> None:
    global publisher_driver

    def update_status(message: str) -> None:
        with publisher_lock:
            publisher_state.update(status="starting", message=message)

    try:
        driver = open_filled_draft(image_paths, title, content, update_status)
    except Exception as exc:
        with publisher_lock:
            publisher_state.update(status="error", message=f"打开小红书草稿失败：{exc}")
        return
    with publisher_lock:
        publisher_driver = driver
        publisher_state.update(
            status="ready",
            message="草稿已填入浏览器。请检查图片顺序、标题和正文，并手动点击发布。",
        )


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalImageCrawler/1.0"

    def send_json(self, value: Any, status: int = 200) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == "/":
            page = PAGE.replace(
                "__DEFAULT_OUTPUT__",
                html.escape(str(DEFAULT_OUTPUT), quote=True),
            )
            payload = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)
            return
        if request.path == "/api/metrics":
            self.send_json(METRIC_NAMES)
            return
        if request.path == "/api/status":
            with job_lock:
                snapshot = {
                    **job,
                    "logs": "\n".join(job["logs"]),
                }
            self.send_json(snapshot)
            return
        if request.path == "/api/mistral-key/status":
            with job_lock:
                configured = mistral_api_key is not None
            self.send_json({"configured": configured})
            return
        if request.path == "/api/publisher/folders":
            self.list_publisher_folders()
            return
        if request.path == "/api/publisher/image":
            self.send_publisher_image(parse_qs(request.query).get("index", [""])[0])
            return
        if request.path == "/api/publisher/status":
            with publisher_lock:
                status = dict(publisher_state)
            self.send_json(status)
            return
        if request.path == "/api/manage/list":
            try:
                relative_path = parse_qs(request.query).get("path", [""])[0]
                self.send_json(list_managed_directory(relative_path))
            except FileNotFoundError as exc:
                self.send_json({"error": str(exc)}, 404)
            except (ValueError, OSError) as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if request.path == "/api/manage/image":
            self.send_managed_image(parse_qs(request.query).get("path", [""])[0])
            return
        self.send_json({"error": "Not found"}, 404)

    def send_managed_image(self, relative_path: str) -> None:
        try:
            image_path = resolve_managed_path(relative_path)
            if (
                not image_path.exists()
                or not image_path.is_file()
                or image_path.is_symlink()
                or image_path.suffix.lower() not in IMAGE_EXTENSIONS
            ):
                raise FileNotFoundError("照片不存在或格式不受支持。")
            payload = image_path.read_bytes()
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, 404)
            return
        except (ValueError, OSError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(image_path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path in {"/api/mistral-key", "/api/mistral-key/clear"}:
            if not self.is_same_origin_request():
                self.send_json({"error": "API Key 请求只允许来自当前本机网页。"}, 403)
                return
            self.update_token()
            return
        if self.path == "/api/rewrite":
            if not self.is_same_origin_request():
                self.send_json({"error": "改写请求只允许来自当前本机网页。"}, 403)
                return
            self.rewrite_metric_queries()
            return
        if self.path == "/api/manage/delete":
            self.delete_library_item()
            return
        if self.path in {"/api/publisher/prepare", "/api/publisher/launch", "/api/publisher/close"}:
            if not self.is_same_origin_request():
                self.send_json({"error": "小红书发布请求只允许来自当前本机网页。"}, 403)
                return
            if self.path == "/api/publisher/prepare":
                self.prepare_publisher_draft()
            elif self.path == "/api/publisher/launch":
                self.launch_publisher_draft()
            else:
                self.close_publisher_browser()
            return
        if self.path != "/api/start":
            self.send_json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("请求内容为空或超过大小限制。")
            payload = json.loads(self.rfile.read(length))
            command = self.make_command(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return

        with job_lock:
            if job["status"] in {"starting", "running"}:
                self.send_json({"error": "已有抓取任务运行中。"}, 409)
                return
            job.update(status="starting", logs=[], returncode=None, error=None)

        worker = threading.Thread(target=run_crawler, args=(command,), daemon=True)
        worker.start()
        self.send_json({"status": "starting"}, 202)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("请求内容为空或超过大小限制。")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("请求格式错误。")
        return payload

    def list_publisher_folders(self) -> None:
        folders: list[dict[str, Any]] = []
        try:
            for folder in ROOT.iterdir():
                if (
                    not folder.is_dir()
                    or folder.is_symlink()
                    or folder.name.lower() in PROTECTED_DIRS
                ):
                    continue
                is_metric = folder.name in METRIC_NAMES
                if is_metric:
                    high_dir = folder / "high"
                    low_dir = folder / "low"
                    if high_dir.is_symlink() or low_dir.is_symlink():
                        continue
                    high_count = count_managed_images(high_dir) if high_dir.is_dir() else 0
                    low_count = count_managed_images(low_dir) if low_dir.is_dir() else 0
                    if not high_count or not low_count:
                        continue
                    image_count = high_count + low_count
                else:
                    image_count = count_managed_images(folder)
                    if not image_count:
                        continue
                folders.append({
                    "name": folder.name,
                    "path": folder.name,
                    "image_count": image_count,
                    "is_metric": is_metric,
                })
        except OSError as exc:
            self.send_json({"error": f"读取素材文件夹失败：{exc}"}, 500)
            return
        self.send_json({"folders": sorted(folders, key=lambda item: item["name"].casefold())})

    def prepare_publisher_draft(self) -> None:
        global publisher_draft
        try:
            payload = self.read_json_body()
            mode = payload.get("mode")
            folder = payload.get("folder")
            count = payload.get("count")
            prompt = payload.get("prompt", "")
            if mode not in {"comparison", "topic"}:
                raise ValueError("请选择有效的发布素材模式。")
            if not isinstance(folder, str) or not folder.strip() or len(folder) > 500:
                raise ValueError("请选择有效的素材文件夹。")
            if isinstance(count, bool) or not isinstance(count, int):
                raise ValueError("抽取数量必须是整数。")
            if not isinstance(prompt, str) or len(prompt) > 2000:
                raise ValueError("创作者 Prompt 不能超过 2000 个字符。")
            requested_folder = ROOT / folder
            if requested_folder.is_symlink():
                raise ValueError("不能使用符号链接作为素材文件夹。")
            selected_folder = requested_folder.resolve()
            if (
                selected_folder.parent != ROOT
                or selected_folder.is_symlink()
                or not selected_folder.is_dir()
                or selected_folder.name.lower() in PROTECTED_DIRS
            ):
                raise ValueError("只能选择项目根目录中可访问的素材文件夹。")
            is_metric = selected_folder.name in METRIC_NAMES
            if (mode == "comparison") != is_metric:
                raise ValueError("所选素材文件夹与当前模式不匹配，请重新选择。")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return

        with publisher_lock:
            if publisher_state["status"] in {"generating", "starting", "ready", "closing"}:
                self.send_json({"error": "当前已有小红书草稿或浏览器任务正在处理中。"}, 409)
                return
            publisher_draft = None
            publisher_state.update(status="generating", message="正在抽取素材并生成文案。")
        with job_lock:
            api_key = mistral_api_key
        if not api_key:
            with publisher_lock:
                publisher_state.update(status="error", message="请先绑定 Mistral API Key。")
            self.send_json({"error": "请先在抓取控制台绑定 Mistral API Key。"}, 400)
            return

        try:
            images, group_counts = build_post_images(ROOT, mode, folder, count)
        except ValueError as exc:
            with publisher_lock:
                publisher_state.update(status="error", message=str(exc))
            self.send_json({"error": str(exc)}, 400)
            return
        except OSError as exc:
            with publisher_lock:
                publisher_state.update(status="error", message=f"素材处理失败：{exc}")
            self.send_json({"error": f"素材处理失败：{exc}"}, 500)
            return

        try:
            copy = generate_copywriting(
                api_key,
                mode,
                selected_folder.name,
                group_counts,
                prompt,
            )
        except RuntimeError as exc:
            with publisher_lock:
                publisher_state.update(status="error", message=str(exc))
            self.send_json({"error": str(exc)}, 502)
            return

        with publisher_lock:
            publisher_draft = {
                "images": images,
                "copy": copy,
                "folder": selected_folder.name,
                "mode": mode,
            }
            publisher_state.update(status="draft", message="草稿已准备好，请先审核图片和文案。")
        self.send_json({
            "images": [{"name": path.name} for path in images],
            "copy": copy,
        })

    def send_publisher_image(self, raw_index: str) -> None:
        try:
            index = int(raw_index)
        except ValueError:
            self.send_json({"error": "图片索引无效。"}, 400)
            return
        with publisher_lock:
            draft = publisher_draft
            if draft is None or not 0 <= index < len(draft["images"]):
                self.send_json({"error": "预览图片不存在或草稿已失效。"}, 404)
                return
            image_path = draft["images"][index]
        try:
            if not image_path.is_file() or image_path.is_symlink():
                raise FileNotFoundError("预览图片不存在。")
            payload = image_path.read_bytes()
        except OSError as exc:
            self.send_json({"error": f"读取预览图片失败：{exc}"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(image_path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def launch_publisher_draft(self) -> None:
        try:
            payload = self.read_json_body()
            title = payload.get("title")
            content = payload.get("content")
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 20:
                raise ValueError("标题不能为空且不能超过 20 个字符。")
            if not isinstance(content, str) or not content.strip() or len(content.strip()) > 1000:
                raise ValueError("正文不能为空且不能超过 1000 个字符。")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with publisher_lock:
            if publisher_draft is None:
                self.send_json({"error": "请先准备并审核一份发布草稿。"}, 409)
                return
            if publisher_state["status"] in {"generating", "starting", "ready", "closing"}:
                self.send_json({"error": "当前小红书草稿已在处理中或已打开。"}, 409)
                return
            publisher_draft["copy"] = {"title": title.strip(), "content": content.strip()}
            image_paths = list(publisher_draft["images"])
            publisher_state.update(status="starting", message="正在启动小红书创作者编辑页。")
        worker = threading.Thread(
            target=run_publisher_browser,
            args=(image_paths, title.strip(), content.strip()),
            daemon=True,
        )
        worker.start()
        self.send_json({"status": "starting", "message": "正在打开小红书编辑页；首次使用请在浏览器中登录。"}, 202)

    def close_publisher_browser(self) -> None:
        global publisher_driver
        with publisher_lock:
            if publisher_state["status"] in {"starting", "closing"}:
                self.send_json({"error": "浏览器正在启动或关闭，请稍后再试。"}, 409)
                return
            driver = publisher_driver
            publisher_driver = None
            publisher_state.update(status="closing", message="正在关闭发布浏览器。")
        if driver is not None:
            try:
                driver.quit()
            except Exception as exc:
                with publisher_lock:
                    publisher_state.update(status="error", message=f"浏览器已退出但清理驱动失败：{exc}")
                self.send_json({"error": f"浏览器已退出但清理驱动失败：{exc}"}, 500)
                return
        with publisher_lock:
            publisher_state.update(status="draft", message="发布浏览器已关闭；草稿仍保留在本机服务内存中。")
        self.send_json({"status": "draft", "message": "发布浏览器已关闭；草稿仍保留在本机服务内存中。"})

    def rewrite_metric_queries(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("请求内容为空或超过大小限制。")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("请求格式错误。")
            metric = payload.get("metric")
            if not isinstance(metric, str) or metric not in METRIC_NAMES:
                raise ValueError("请选择有效的预设指标。")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return

        with job_lock:
            if job["status"] in {"starting", "running"}:
                self.send_json({"error": "抓取任务运行期间不能改写搜索词。"}, 409)
                return
            api_key = mistral_api_key
        if api_key is None:
            self.send_json({"error": "请先绑定 Mistral API Key。"}, 400)
            return

        child_env = os.environ.copy()
        child_env.pop("HF_TOKEN", None)
        child_env.pop("HUGGINGFACEHUB_API_TOKEN", None)
        child_env["MISTRAL_API_KEY"] = api_key
        try:
            result = subprocess.run(
                [sys.executable, str(SCRAPER), "--rewrite-metric", metric],
                cwd=ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.send_json({"error": "调用 Ministral 14B 超时，请检查网络后重试。"}, 504)
            return
        except OSError as exc:
            self.send_json({"error": f"无法启动搜索词改写：{exc}"}, 500)
            return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            self.send_json(
                {"error": f"搜索词改写失败：{detail[-1500:] or '模型调用异常。'}"},
                502,
            )
            return
        try:
            queries = json.loads(result.stdout)
            if (
                not isinstance(queries, dict)
                or not isinstance(queries.get("high"), str)
                or not isinstance(queries.get("low"), str)
            ):
                raise ValueError("模型结果中缺少 high / low 搜索词。")
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": f"无法解析模型改写结果：{exc}"}, 502)
            return
        self.send_json({"model": "ministral-14b-2512", "queries": queries})

    def is_same_origin_request(self) -> bool:
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if not origin or not host:
            return False
        try:
            parsed_origin = urlsplit(origin)
            parsed_host = urlsplit(f"http://{host}")
        except ValueError:
            return False
        return (
            parsed_origin.scheme == "http"
            and parsed_origin.netloc.casefold() == host.casefold()
            and parsed_host.hostname in {"127.0.0.1", "localhost"}
        )

    def update_token(self) -> None:
        global mistral_api_key
        is_clear = self.path == "/api/mistral-key/clear"
        if is_clear:
            token = None
        else:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("请求内容为空或超过大小限制。")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("请求格式错误。")
                token_value = payload.get("api_key")
                if not isinstance(token_value, str):
                    raise ValueError("请输入有效的 Mistral API Key。")
                token = token_value.strip()
                if not token or len(token) > 4096 or any(ord(char) < 32 for char in token):
                    raise ValueError("API Key 不能为空、不能超过 4096 个字符，也不能包含控制字符。")
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, 400)
                return

        with job_lock:
            mistral_api_key = token
        self.send_json({"configured": token is not None})

    def delete_library_item(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError("请求内容为空或超过大小限制。")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("请求格式错误。")
            with job_lock:
                if job["status"] in {"starting", "running"}:
                    self.send_json({"error": "抓取任务运行期间不能删除文件。"}, 409)
                    return
            delete_managed_item(payload.get("path"), payload.get("kind"))
        except FileNotFoundError as exc:
            self.send_json({"error": str(exc)}, 404)
            return
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        except OSError as exc:
            self.send_json({"error": f"文件操作失败：{exc}"}, 500)
            return
        self.send_json({"deleted": True})

    def make_command(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            raise ValueError("请求格式错误。")
        mode = payload.get("mode")
        threshold = payload.get("threshold")
        target_count = payload.get("target_count")
        output_dir = payload.get("output_dir") or str(DEFAULT_OUTPUT)
        if mode not in {"metrics", "custom"}:
            raise ValueError("请选择指标改写或自定义话题模式。")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.35 <= threshold <= 0.95:
            raise ValueError("CLIP 严格度必须在 0.35 到 0.95 之间。")
        if isinstance(target_count, bool) or not isinstance(target_count, int) or not 1 <= target_count <= 1000:
            raise ValueError("每个级别目标图片数必须在 1 到 1000 之间。")
        if not isinstance(output_dir, str) or not output_dir.strip() or len(output_dir) > 1000:
            raise ValueError("请填写有效的图片保存目录。")

        command = [
            sys.executable,
            str(SCRAPER),
            "--target-count",
            str(target_count),
            "--clip-threshold",
            f"{threshold:.2f}",
            "--output-dir",
            str(
                (ROOT / Path(output_dir).expanduser()).resolve()
                if not Path(output_dir).expanduser().is_absolute()
                else Path(output_dir).expanduser().resolve()
            ),
        ]
        if mode == "custom":
            topic = payload.get("custom_topic")
            if not isinstance(topic, str) or not topic.strip() or len(topic) > 240:
                raise ValueError("自定义搜索话题不能为空，且不能超过 240 个字符。")
            command.extend(["--custom-topic", topic.strip()])
        else:
            metrics = payload.get("metrics")
            if not isinstance(metrics, list) or len(metrics) != 1:
                raise ValueError("请选择一个指标。")
            if not all(isinstance(name, str) and name in METRIC_NAMES for name in metrics):
                raise ValueError("指标列表包含无效选项，请刷新页面后重试。")
            rewritten_queries = payload.get("rewritten_queries")
            if not isinstance(rewritten_queries, dict):
                raise ValueError("请先改写并确认该指标的 high / low 搜索词。")
            query_high = rewritten_queries.get("high")
            query_low = rewritten_queries.get("low")
            if (
                not isinstance(query_high, str)
                or not query_high.strip()
                or len(query_high) > 300
                or not isinstance(query_low, str)
                or not query_low.strip()
                or len(query_low) > 300
            ):
                raise ValueError("改写后的 high / low 搜索词无效。请重新改写。")
            command.extend([
                "--metric", metrics[0],
                "--rewritten-query-high", query_high.strip(),
                "--rewritten-query-low", query_low.strip(),
            ])
        return command

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} {format_string % args}")


def main() -> None:
    port = int(os.getenv("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"图片抓取控制台已启动：http://127.0.0.1:{port}")
    print("关闭此终端即可停止网页服务；抓取任务运行期间请保持窗口开启。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止网页服务…")
    finally:
        server.server_close()
        if publisher_driver is not None:
            try:
                publisher_driver.quit()
            except Exception as exc:
                print(f"关闭小红书浏览器失败：{exc}")


if __name__ == "__main__":
    main()
