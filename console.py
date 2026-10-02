"""Local web interface for configuring and running the image crawler."""

from __future__ import annotations

import ast
import html
import json
import mimetypes
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from xiaohongshu_publisher.copywriter import generate_copywriting
from xiaohongshu_publisher.image_loader import build_post_images, candidate_key, list_candidate_images
from xiaohongshu_publisher.publisher import (
    BROWSERS,
    DEFAULT_BROWSER,
    PublisherEditorNotFound,
    PublisherManualIntervention,
    browser_alive,
    click_publish,
    installed_browsers,
    open_filled_draft,
)


ROOT = Path(__file__).resolve().parent
SCRAPER = ROOT / "scraper.py"
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
mistral_api_key: str | None = "mstrl_HxnjXXBJ1UwwLnWKPWcpOfUaJZOdcBEN_3Y7C4t"
publisher_lock = threading.Lock()
publisher_state: dict[str, str] = {"status": "idle", "message": ""}
publisher_draft: dict[str, Any] | None = None
publisher_driver: Any = None
AUTO_MIN_INTERVAL_SECONDS = 10
AUTO_MAX_CONSECUTIVE_FAILURES = 3
auto_stop_event = threading.Event()
auto_state: dict[str, Any] = {
    "status": "idle",
    "message": "",
    "published": 0,
    "target": 0,
    "next_at": None,
    "log": [],
}


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
  <title>图片收集小助手</title>
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
    .check-row { display:flex; align-items:center; gap:8px; margin:14px 0 0; color:#24292d; font-weight:600; cursor:pointer; }
    .sub-tabs { display:grid; grid-template-columns:1fr 1fr; gap:4px; margin:0 0 18px; padding:4px; border-radius:12px; background:#e6eaed; }
    .sub-tabs button { display:flex; flex-direction:column; align-items:center; gap:2px; padding:10px 12px; border:0; border-radius:9px; background:transparent; color:#5b646b; cursor:pointer; transition:background .15s, color .15s, box-shadow .15s; }
    .sub-tabs button:hover { color:#24292d; }
    .sub-tabs button[aria-current="page"] { background:#fff; color:#174f77; box-shadow:0 1px 3px rgba(0,0,0,.12); }
    .sub-tabs button:focus-visible { outline:2px solid #174f77; outline-offset:2px; }
    .sub-tab-title { font-size:15px; font-weight:650; }
    .sub-tab-desc { font-size:12px; color:#7a848b; }
    @media(max-width:520px) { .sub-tab-desc { display:none; } }
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
    #confirm-dialog { width:min(92vw,440px); padding:20px; border:1px solid #ccd3d8; border-radius:6px; background:#fff; box-shadow:0 18px 70px rgba(0,0,0,.35); }
    #confirm-dialog::backdrop { background:rgba(12,17,21,.55); }
    #confirm-message { margin:0 0 18px; white-space:pre-wrap; overflow-wrap:anywhere; color:#24292d; line-height:1.6; }
    .confirm-actions { display:flex; justify-content:flex-end; gap:10px; }
    #preview-image { display:block; max-width:100%; max-height:calc(90vh - 90px); margin:0 auto; object-fit:contain; }
    .preview-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px; }
    #preview-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    #publisher-images { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:10px; margin:16px 0; }
    .publisher-image { min-width:0; padding:7px; border:1px solid #d9dddf; background:#fafbfb; }
    .publisher-image img { width:100%; height:120px; object-fit:cover; }
    .publisher-image span { display:block; overflow:hidden; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
    .picker-group h3 { margin:14px 0 8px; font-size:15px; }
    .picker-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(96px,1fr)); gap:8px; max-height:420px; overflow:auto; }
    .picker-item { position:relative; padding:0; border:2px solid transparent; background:#fafbfb; cursor:pointer; }
    .picker-item img { display:block; width:100%; height:96px; object-fit:cover; }
    .picker-item.selected { border-color:#245b7c; }
    .picker-item .picker-order { position:absolute; top:4px; right:4px; min-width:22px; height:22px; border-radius:11px; background:#245b7c; color:#fff; font-size:12px; line-height:22px; text-align:center; }
    .field-label { display:block; margin-bottom:8px; color:#24292d; font-weight:650; }
    .wheel-picker { position:relative; display:flex; gap:4px; width:max-content; padding:0 12px; background:#fff; border:1px solid #d9dddf; border-radius:14px; user-select:none; }
    .wheel-column { position:relative; display:flex; align-items:center; }
    .wheel { width:64px; height:180px; overflow-y:scroll; scroll-snap-type:y mandatory; scrollbar-width:none; padding:72px 0; box-sizing:border-box; outline:none;
      -webkit-mask-image:linear-gradient(transparent, #000 35%, #000 65%, transparent); mask-image:linear-gradient(transparent, #000 35%, #000 65%, transparent); }
    .wheel::-webkit-scrollbar { display:none; }
    .wheel div { height:36px; line-height:36px; text-align:right; padding-right:6px; color:#1c1c1e; font-size:22px; font-variant-numeric:tabular-nums; scroll-snap-align:center; cursor:pointer; }
    .wheel:focus-visible { box-shadow:inset 0 0 0 2px #0a84ff; border-radius:10px; }
    .wheel-unit { width:44px; color:#1c1c1e; font-size:16px; font-weight:600; position:relative; z-index:1; }
    .wheel-highlight { position:absolute; left:8px; right:8px; top:72px; height:36px; border-radius:8px; background:rgba(0,0,0,.06); pointer-events:none; }
    #auto-state { min-height:24px; color:#245b7c; font-weight:650; }
    #auto-log { max-height:220px; overflow:auto; margin:8px 0 0; padding-left:18px; color:#555d63; font-size:13px; }
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
    <a class="brand" href="https://www.yanzumeixue.com/" target="_blank" rel="noopener noreferrer" aria-label="颜祖美学官网">
      <img src="https://www.yanzumeixue.com/images/yanzu-meixue.svg" alt="颜祖美学 Logo">
      <span>颜祖美学</span>
    </a>
  </div>
</nav>
<main>
  <header class="hero">
    <div>
      <p class="eyebrow">IMAGE RESEARCH / LOCAL TOOL</p>
      <h1>图片收集小助手</h1>
    </div>
    <div class="hero-copy">
      <p>从预设的外貌特征或自定义话题出发，收集有趣的图片样本。</p>
      <p>设置挑选标准，让每次收集都更有方向。</p>
      <span class="badge">只在你的电脑本地运行 · 安全放心</span>
    </div>
  </header>
    <nav class="nav-actions" aria-label="页面">
      <button type="button" id="show-crawler" aria-current="page">收集面板</button>
      <button type="button" id="show-manager">图片管理</button>
      <button type="button" id="show-publisher">小红书助手</button>
    </nav>
    <section id="publisher-page" hidden>
      <nav class="sub-tabs" aria-label="小红书助手">
        <button type="button" id="show-publisher-manual" aria-current="page">
          <span class="sub-tab-title">图文一键准备</span>
          <span class="sub-tab-desc">选图 + 写文案，人工审核后发布</span>
        </button>
        <button type="button" id="show-publisher-auto">
          <span class="sub-tab-title">全自动发布</span>
          <span class="sub-tab-desc">按间隔自动抽图、写文案、发布</span>
        </button>
      </nav>
      <div id="publisher-manual-view">
      <section class="panel">
        <h2>小红书图文一键准备</h2>
        <p>从本地图片文件夹里挑选照片，用智能助手自动写好文案并预览；最后会自动加上一张好看的宣传图。</p>
        <div class="warning">勾选“填好后自动点击发布”时会直接发到小红书，请先在下方检查图片和文字；取消勾选则只填入草稿，由你确认后自己点击“发布”。</div>
        <div class="field">
          <label for="publisher-mode">选择类型</label>
          <select id="publisher-mode">
            <option value="comparison">63 种外貌特征：高低对比</option>
            <option value="topic">自定义话题文件夹：自由写文案</option>
          </select>
        </div>
        <div class="field">
          <label for="publisher-folder">图片文件夹</label>
          <select id="publisher-folder"></select>
          <p class="help" id="publisher-folder-help"></p>
        </div>
        <div class="field">
          <label for="publisher-pick-mode">选图方式</label>
          <select id="publisher-pick-mode">
            <option value="random">随机抽取</option>
            <option value="manual">自己筛选</option>
          </select>
        </div>
        <div class="field" id="publisher-picker" hidden>
          <p class="help" id="publisher-picker-help">点击图片勾选，按勾选顺序排列。</p>
          <div id="publisher-picker-groups"></div>
        </div>
        <div class="field" id="publisher-count-field">
          <label for="publisher-count">挑选数量</label>
          <input id="publisher-count" type="number" min="1" max="8" value="3">
          <p class="help" id="publisher-count-help">“数值高”和“数值低”两边各抽取此数量；最多 8 张/组。最后会附加推广图。</p>
        </div>
        <div class="field">
          <label for="publisher-prompt">给AI的写作要求</label>
          <textarea id="publisher-prompt" maxlength="2000" placeholder="比如：语气要轻松活泼、重点突出等"></textarea>
        </div>
        <button type="button" class="submit" id="prepare-publisher">随机选图并写文案</button>
        <p id="publisher-state" role="status" aria-live="polite">先选择图片文件夹，再生成草稿。</p>
      </section>
      <section class="panel" id="publisher-preview-panel" hidden>
        <h2>效果预览</h2>
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
        <div class="field">
          <label for="publisher-visibility">谁可以看</label>
          <select id="publisher-visibility">
            <option value="public">公开（public）</option>
            <option value="private">仅自己可见（private）</option>
          </select>
        </div>
        <div class="field">
          <label for="publisher-browser">发布使用的浏览器</label>
          <select id="publisher-browser" class="browser-select">
            <option value="edge">Microsoft Edge（默认）</option>
            <option value="chrome">Google Chrome</option>
            <option value="firefox">Firefox</option>
          </select>
          <p class="help">每种浏览器第一次使用时都需要在弹出的窗口里登录一次小红书。</p>
        </div>
        <label class="check-row"><input type="checkbox" id="publisher-auto-click" checked> 填好后自动点击“发布”</label>
        <div class="publisher-actions">
          <button type="button" class="item-action" id="regenerate-publisher">换一组图片和文案</button>
          <button type="button" class="submit" id="open-publisher">打开小红书并自动发布</button>
          <button type="button" class="item-action" id="close-publisher" hidden>关闭小红书浏览器</button>
        </div>
      </section>
      </div>
      <div id="publisher-auto-view" hidden>
      <section class="panel" id="auto-panel">
        <h2>全自动文案发布</h2>
        <p>每次从所选文件夹随机抽图、自动写文案并<strong>直接点击发布</strong>，然后按间隔循环。</p>
        <div class="warning">开启后会真实发到你的小红书账号上，不再经过人工审核。建议先设为“仅自己可见”试跑一篇；间隔太短可能触发平台限流。</div>
        <div class="field">
          <label for="auto-folder">图片文件夹</label>
          <select id="auto-folder"></select>
        </div>
        <div class="field">
          <label for="auto-count">每篇挑选数量</label>
          <input id="auto-count" type="number" min="1" max="8" value="3">
          <p class="help">外貌特征文件夹：“数值高”和“数值低”各抽此数量；话题文件夹：共抽此数量。最多 8 张，最后会附加推广图。</p>
        </div>
        <div class="field">
          <label for="auto-prompt">给AI的写作要求</label>
          <textarea id="auto-prompt" maxlength="2000" placeholder="比如：语气要轻松活泼、重点突出等"></textarea>
        </div>
        <div class="field">
          <label for="auto-visibility">谁可以看</label>
          <select id="auto-visibility">
            <option value="public">公开（public）</option>
            <option value="private">仅自己可见（private）</option>
          </select>
        </div>
        <div class="field">
          <label for="auto-browser">发布使用的浏览器</label>
          <select id="auto-browser" class="browser-select">
            <option value="edge">Microsoft Edge（默认）</option>
            <option value="chrome">Google Chrome</option>
            <option value="firefox">Firefox</option>
          </select>
          <p class="help">每种浏览器第一次使用时都需要在弹出的窗口里登录一次小红书。</p>
        </div>
        <div class="field">
          <span class="field-label" id="auto-interval-label">发布间隔</span>
          <div class="wheel-picker" role="group" aria-labelledby="auto-interval-label">
            <div class="wheel-column">
              <div class="wheel" id="auto-hours" tabindex="0" role="listbox" aria-label="小时"></div>
              <span class="wheel-unit">小时</span>
            </div>
            <div class="wheel-column">
              <div class="wheel" id="auto-minutes" tabindex="0" role="listbox" aria-label="分钟"></div>
              <span class="wheel-unit">分钟</span>
            </div>
            <div class="wheel-column">
              <div class="wheel" id="auto-seconds" tabindex="0" role="listbox" aria-label="秒"></div>
              <span class="wheel-unit">秒</span>
            </div>
            <div class="wheel-highlight" aria-hidden="true"></div>
          </div>
          <p class="help" id="auto-interval-help"></p>
        </div>
        <div class="field">
          <label for="auto-target">发布篇数</label>
          <input id="auto-target" type="number" min="0" max="100" value="0">
          <p class="help">填 0 表示不限，直到手动停止。</p>
        </div>
        <div class="publisher-actions">
          <button type="button" class="submit" id="auto-start">开始自动发布</button>
          <button type="button" class="item-action" id="auto-stop" hidden>停止自动发布</button>
        </div>
        <p id="auto-state" role="status" aria-live="polite">未启动。</p>
        <ul id="auto-log"></ul>
      </section>
      </div>
    </section>
    <section id="manager-page" hidden>
      <section class="panel">
        <h2>图片文件夹管理</h2>
        <p>管理电脑里的图片。删除文件夹会把里面的东西全部清空，操作时要小心哦。</p>
        <p class="help">系统重要文件夹会自动受到保护，不会被误删。</p>
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
    <dialog id="confirm-dialog">
      <form method="dialog">
        <p id="confirm-message"></p>
        <div class="confirm-actions">
          <button type="submit" class="item-action" value="cancel">取消</button>
          <button type="submit" class="item-action" id="confirm-ok" value="ok">确定</button>
        </div>
      </form>
    </dialog>
    <section id="crawler-page">
    <form id="crawl-form">
    <section class="panel">
      <h2>1. 选择要收集的内容</h2>
      <div class="mode">
        <label><input type="radio" name="mode" value="metrics" checked> 选择一个外貌特征 + 智能助手优化词语</label>
        <label><input type="radio" name="mode" value="custom"> 自定义搜索词</label>
      </div>
      <div id="metric-section" class="field">
        <div class="toolbar">
          <input id="metric-filter" type="text" placeholder="搜索外貌特征名字">
          <span class="help" id="selected-count">请选择一个外貌特征</span>
        </div>
        <div id="metrics" aria-label="63 种外貌特征列表"></div>
        <p class="help" id="metric-help">选好特征后点“优化搜索词”，检查一下高/低搜索词，就可以开始收集了。</p>
        <p class="help">保存文件夹始终使用改写前选中的指标名称；改写后的搜索词只用于检索，不会改变文件夹名。</p>
        <p class="help">图片主要从知名外貌讨论网站的搜索结果中寻找。</p>
        <p class="help">智能助手：大语言模型（云端安全调用）</p>
        <label for="mistral-api-key">密钥 (API Key)</label>
        <div class="token-controls">
          <input id="mistral-api-key" type="password" autocomplete="new-password" spellcheck="false" placeholder="粘贴 密钥 (API Key)" aria-describedby="token-help token-status">
          <button type="button" id="bind-token">保存密钥</button>
          <button type="button" id="clear-token">清除密钥</button>
        </div>
        <p class="help" id="token-help">密钥只临时保存在你的电脑内存里，非常安全，关掉软件后就会自动消失。</p>
        <p id="token-status" role="status" aria-live="polite" data-configured="false">正在检查密钥状态…</p>
        <button type="button" id="rewrite-query">优化搜索词</button>
        <div id="rewritten-queries" class="field" aria-live="polite" hidden>
          <p><strong>高特征搜索词</strong></p>
          <pre id="rewritten-high"></pre>
          <p><strong>低特征搜索词</strong></p>
          <pre id="rewritten-low"></pre>
        </div>
      </div>
      <div id="custom-section" class="field" hidden>
        <label for="custom-topic">自定义搜索关键词</label>
        <input id="custom-topic" type="text" maxlength="240" placeholder="例如：帅气男生侧脸写真">
        <p class="help">这个词会直接用来搜图片，也会作为保存文件夹的名字。</p>
      </div>
      <div class="field">
        <label for="search-source">图片搜索来源</label>
        <select id="search-source">
          <option value="looksmax">looksmax.org（外貌讨论站，适合外貌特征）</option>
          <option value="bing">Bing 全网图片</option>
          <option value="baidu">百度图片（适合国内明星）</option>
          <option value="so360">360 图片（国内）</option>
        </select>
        <p class="help" id="search-source-help"></p>
      </div>
    </section>
    <section class="panel">
      <h2>2. 设置挑选和保存要求</h2>
      <div class="field">
        <label for="threshold">图片挑选严格程度</label>
        <div class="range-row">
          <span class="help">宽松</span>
          <input id="threshold" type="range" min="0.35" max="0.95" step="0.01" value="0.60">
          <span class="help">严格</span>
          <output id="threshold-value" for="threshold">0.60 · 标准</output>
        </div>
        <p class="help">数值越高，系统对“照片清晰、只有一个人、真人、眼睛能看清”的要求就越严格，挑出来的照片会更少但质量更高。</p>
      </div>
      <div class="grid">
        <div class="field">
          <label for="target-count">每个分类需要的图片数量</label>
          <input id="target-count" type="number" min="1" max="1000" value="20">
        </div>
        <div class="field">
          <label for="output-dir">图片保存的文件夹位置</label>
          <input id="output-dir" type="text" value="__DEFAULT_OUTPUT__">
          <p class="help">默认保存在软件同级文件夹中，会自动用特征名字建文件夹。</p>
        </div>
      </div>
      <div class="warning">请注意遵守网络版权和肖像权。这只是电脑自动挑选助手，不能代替专业测量。</div>
    </section>
    <button class="submit" id="start" type="submit">开始收集图片</button>
  </form>
  <section class="panel" aria-live="polite">
    <h2>当前任务状态</h2>
    <div id="status">空闲</div>
    <pre id="logs">还没有开始收集任务。</pre>
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
// 用页面内对话框代替 window.confirm：部分内嵌浏览器会直接把 confirm 当成“取消”。
function askConfirm(message, {okText = "确定", danger = false} = {}) {
  const dialog = document.getElementById("confirm-dialog");
  const okButton = document.getElementById("confirm-ok");
  document.getElementById("confirm-message").textContent = message;
  okButton.textContent = okText;
  okButton.classList.toggle("danger", danger);
  dialog.returnValue = "cancel";
  dialog.showModal();
  return new Promise(resolve => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), {once:true});
  });
}
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

const SEARCH_SOURCE_HELP = {
  looksmax: "在 looksmax.org 站内搜索；中文搜索词会先翻译成英文。",
  bing: "在 Bing 搜索全网图片，搜索词不做翻译。",
  baidu: "在百度图片搜索；所有搜索词会先翻译成中文，适合搜索国内明星。",
  so360: "在 360 图片搜索；所有搜索词会先翻译成中文。",
};
function updateSearchSourceHelp() {
  const source = document.getElementById("search-source").value;
  document.getElementById("search-source-help").textContent = SEARCH_SOURCE_HELP[source];
}
document.getElementById("search-source").addEventListener("change", updateSearchSourceHelp);
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
    : "请选择一个外貌特征";
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
      ? "密钥 (API Key) 已绑定到本机服务（只显示状态，不回显密钥）。"
      : "尚未绑定 密钥 (API Key)；优化搜索词前请先绑定。";
  } catch (error) {
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = `API Key 状态读取失败：${error.message}`;
  }
}
document.getElementById("bind-token").addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) {
    tokenStatus.dataset.configured = "false";
    tokenStatus.textContent = "请先输入 密钥 (API Key)。";
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
    tokenStatus.textContent = "密钥 (API Key) 已绑定到本机服务内存；页面不会保存或回显它。";
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
    tokenStatus.textContent = "密钥 (API Key) 已从本机服务内存中清除。";
  } catch (error) {
    tokenStatus.textContent = `API Key 清除失败：${error.message}`;
  } finally {
    button.disabled = false;
  }
});
document.querySelectorAll('input[name="mode"]').forEach(item => item.addEventListener("change", () => {
  // 切换模式时给出推荐来源：外貌特征用 looksmax，自定义关键词用百度
  document.getElementById("search-source").value = item.value === "custom" ? "baidu" : "looksmax";
  updateSearchSourceHelp();
  updateMode();
}));
updateSearchSourceHelp();
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
    tokenStatus.textContent = `已用 ${data.model} 改写。搜索限定于 looksmax.org；请检查高/低搜索词结果后再开始收集。`;
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
  if (!await askConfirm(`确定永久删除${target}吗？\n\n${path}`, {okText:"删除", danger:true})) return;
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
    ? "“数值高”和“数值低”两边各抽取此数量；最多 8 张/组。最后会附加推广图。"
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
    ? "只显示含“数值高”和“数值低”两个图片子文件夹的外貌特征。"
    : "只显示普通话题文件夹；指标文件夹会从此列表中排除。";
  loadPublisherCandidates();
}
let publisherSelection = [];
let publisherCandidateRequest = 0;
function publisherIsManual() {
  return document.getElementById("publisher-pick-mode").value === "manual";
}
function updatePublisherPickMode() {
  const manual = publisherIsManual();
  document.getElementById("publisher-count-field").hidden = manual;
  document.getElementById("publisher-picker").hidden = !manual;
  document.getElementById("prepare-publisher").textContent = manual ? "用选中的图片写文案" : "随机选图并写文案";
  loadPublisherCandidates();
}
function renderPickerOrder() {
  for (const item of document.querySelectorAll("#publisher-picker-groups .picker-item")) {
    const position = publisherSelection.indexOf(item.dataset.path);
    item.classList.toggle("selected", position !== -1);
    item.setAttribute("aria-pressed", String(position !== -1));
    item.querySelector(".picker-order").hidden = position === -1;
    item.querySelector(".picker-order").textContent = position + 1;
  }
  const counts = [...document.querySelectorAll("#publisher-picker-groups .picker-group")].map(group =>
    `${group.dataset.name} ${group.querySelectorAll(".picker-item.selected").length} 张`);
  document.getElementById("publisher-picker-help").textContent =
    `点击图片勾选，按勾选顺序排列（每组最多 ${publisherGroupLimit()} 张）。已选：${counts.join("，")}`;
}
function publisherGroupLimit() {
  return document.getElementById("publisher-mode").value === "comparison" ? 8 : 17;
}
async function loadPublisherCandidates() {
  const root = document.getElementById("publisher-picker-groups");
  publisherSelection = [];
  root.replaceChildren();
  if (!publisherIsManual()) return;
  const mode = document.getElementById("publisher-mode").value;
  const folder = document.getElementById("publisher-folder").value;
  const help = document.getElementById("publisher-picker-help");
  if (!folder) {
    help.textContent = "先选择图片文件夹，再从下面挑图。";
    return;
  }
  const requestId = ++publisherCandidateRequest;
  help.textContent = "正在读取图片列表…";
  try {
    const params = new URLSearchParams({mode, folder});
    const response = await fetch(`/api/publisher/candidates?${params}`, {cache:"no-store"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "读取图片列表失败");
    if (requestId !== publisherCandidateRequest) return;
    for (const group of data.groups) {
      const section = document.createElement("div");
      section.className = "picker-group";
      section.dataset.name = group.name;
      const heading = document.createElement("h3");
      heading.textContent = `${group.name}（${group.images.length} 张）`;
      const grid = document.createElement("div");
      grid.className = "picker-grid";
      for (const image of group.images) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "picker-item";
        item.dataset.path = image.path;
        item.title = image.name;
        const preview = document.createElement("img");
        preview.loading = "lazy";
        preview.alt = image.name;
        preview.src = `/api/publisher/candidate-image?${new URLSearchParams({mode, folder, path:image.path})}`;
        const order = document.createElement("span");
        order.className = "picker-order";
        order.hidden = true;
        item.append(preview, order);
        item.addEventListener("click", () => {
          const position = publisherSelection.indexOf(image.path);
          if (position !== -1) {
            publisherSelection.splice(position, 1);
          } else if (section.querySelectorAll(".picker-item.selected").length >= publisherGroupLimit()) {
            document.getElementById("publisher-state").textContent = `“${group.name}”最多选择 ${publisherGroupLimit()} 张。`;
            return;
          } else {
            publisherSelection.push(image.path);
          }
          renderPickerOrder();
        });
        grid.append(item);
      }
      section.append(heading, grid);
      root.append(section);
    }
    renderPickerOrder();
  } catch (error) {
    if (requestId === publisherCandidateRequest) help.textContent = `读取图片列表失败：${error.message}`;
  }
}
const BROWSER_STORAGE_KEY = "publisherBrowser";
function renderBrowserOptions(installed) {
  let saved = null;
  try { saved = localStorage.getItem(BROWSER_STORAGE_KEY); } catch (error) {}
  for (const select of document.querySelectorAll(".browser-select")) {
    for (const option of select.options) {
      const ok = installed.includes(option.value);
      option.disabled = !ok;
      option.textContent = option.textContent.replace("（未安装）", "") + (ok ? "" : "（未安装）");
    }
    const preferred = [saved, "edge", ...installed].find(value => value && installed.includes(value));
    if (preferred) select.value = preferred;
  }
}
document.querySelectorAll(".browser-select").forEach(select => select.addEventListener("change", () => {
  try { localStorage.setItem(BROWSER_STORAGE_KEY, select.value); } catch (error) {}
  document.querySelectorAll(".browser-select").forEach(other => { other.value = select.value; });
}));
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
    updateAutoFolders();
    renderBrowserOptions(data.browsers || []);
  } catch (error) {
    document.getElementById("publisher-state").textContent = `读取图片文件夹失败：${error.message}`;
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
    `${data.images.length - 1} 张素材图片 + 最后一张彦祖美学推广图`;
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
    document.getElementById("publisher-state").textContent = "请先选择图片文件夹。";
    return;
  }
  const manual = publisherIsManual();
  if (manual && !publisherSelection.length) {
    document.getElementById("publisher-state").textContent = "请先在下方勾选要发布的图片。";
    return;
  }
  button.disabled = true;
  document.getElementById("publisher-preview-panel").hidden = true;
  document.getElementById("publisher-state").textContent = manual
    ? "正在用选中的图片请求 Ministral 14B 生成文案…"
    : "正在随机抽图并请求 Ministral 14B 生成文案…";
  try {
    const response = await fetch("/api/publisher/prepare", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        mode,
        folder,
        count,
        selected:manual ? publisherSelection : null,
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
document.getElementById("publisher-folder").addEventListener("change", loadPublisherCandidates);
document.getElementById("publisher-pick-mode").addEventListener("change", updatePublisherPickMode);
document.getElementById("prepare-publisher").addEventListener("click", preparePublisherDraft);
document.getElementById("regenerate-publisher").addEventListener("click", preparePublisherDraft);
function updateOpenPublisherLabel() {
  document.getElementById("open-publisher").textContent = document.getElementById("publisher-auto-click").checked
    ? "打开小红书并自动发布"
    : "打开小红书并自动填入草稿";
}
document.getElementById("publisher-auto-click").addEventListener("change", updateOpenPublisherLabel);
updateOpenPublisherLabel();
document.getElementById("open-publisher").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/api/publisher/launch", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        title:document.getElementById("publisher-title").value,
        content:document.getElementById("publisher-content").value,
        visibility:document.getElementById("publisher-visibility").value,
        browser:document.getElementById("publisher-browser").value,
        auto_publish:document.getElementById("publisher-auto-click").checked
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
      data.status === "starting" || data.status === "closing";
    document.getElementById("close-publisher").hidden = data.status !== "ready";
    clearTimeout(publisherTimer);
    if (data.status === "starting") publisherTimer = setTimeout(pollPublisherStatus, 1500);
    else if (data.status === "ready") publisherTimer = setTimeout(pollPublisherStatus, 4000);
  } catch (error) {
    document.getElementById("publisher-state").textContent = `发布状态读取失败：${error.message}`;
  }
}
function showPublisherView(auto) {
  document.getElementById("publisher-manual-view").hidden = auto;
  document.getElementById("publisher-auto-view").hidden = !auto;
  const [on, off] = auto
    ? ["show-publisher-auto", "show-publisher-manual"]
    : ["show-publisher-manual", "show-publisher-auto"];
  document.getElementById(on).setAttribute("aria-current", "page");
  document.getElementById(off).removeAttribute("aria-current");
  if (auto) {
    requestAnimationFrame(syncWheels);
    pollAutoStatus();
  }
}
document.getElementById("show-publisher-manual").addEventListener("click", () => showPublisherView(false));
document.getElementById("show-publisher-auto").addEventListener("click", () => showPublisherView(true));
const AUTO_RANDOM_FOLDER = "__random__";
function updateAutoFolders() {
  const select = document.getElementById("auto-folder");
  const previous = select.value;
  const available = publisherFolders;
  select.replaceChildren(available.length
    ? new Option(`每篇随机抽取一个文件夹（${available.length} 个可选）`, AUTO_RANDOM_FOLDER)
    : new Option("没有可用的文件夹", ""));
  for (const folder of available) {
    const kind = folder.is_metric ? "外貌特征" : "话题";
    select.append(new Option(`${folder.name} · ${kind} · ${folder.image_count} 张照片`, folder.path));
  }
  if (previous && [...select.options].some(option => option.value === previous)) select.value = previous;
}
const WHEEL_ROW = 36;
// 滚轮第 index 行的值是 index * step（秒轮按 10 秒一格）。
function buildWheel(id, max, step, initial) {
  const wheel = document.getElementById(id);
  const lastIndex = Math.floor(max / step);
  for (let index = 0; index <= lastIndex; index += 1) {
    const row = document.createElement("div");
    row.role = "option";
    row.textContent = index * step;
    row.addEventListener("click", () => wheel.scrollTo({top:index * WHEEL_ROW, behavior:"smooth"}));
    wheel.append(row);
  }
  wheel.addEventListener("keydown", event => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const next = Math.min(lastIndex, Math.max(0, wheelIndex(wheel) + (event.key === "ArrowDown" ? 1 : -1)));
    wheel.scrollTo({top:next * WHEEL_ROW, behavior:"smooth"});
  });
  // 选中行记在 data-index 上：面板隐藏时 scrollTop 恒为 0，不能直接读取。
  wheel.dataset.index = initial / step;
  wheel.dataset.step = step;
  let settle = null;
  wheel.addEventListener("scroll", () => {
    if (!wheel.clientHeight) return;
    clearTimeout(settle);
    settle = setTimeout(() => {
      wheel.dataset.index = Math.min(lastIndex, Math.round(wheel.scrollTop / WHEEL_ROW));
      updateAutoIntervalHelp();
    }, 120);
  });
  return wheel;
}
function wheelIndex(wheel) {
  return Number(wheel.dataset.index);
}
function wheelValue(wheel) {
  return wheelIndex(wheel) * Number(wheel.dataset.step);
}
const autoHours = buildWheel("auto-hours", 23, 1, 1);
const autoMinutes = buildWheel("auto-minutes", 59, 1, 0);
const autoSeconds = buildWheel("auto-seconds", 50, 10, 0);
const autoWheels = [autoHours, autoMinutes, autoSeconds];
function syncWheels() {
  for (const wheel of autoWheels) wheel.scrollTop = wheelIndex(wheel) * WHEEL_ROW;
}
updateAutoIntervalHelp();
function autoIntervalSeconds() {
  return wheelValue(autoHours) * 3600 + wheelValue(autoMinutes) * 60 + wheelValue(autoSeconds);
}
function updateAutoIntervalHelp() {
  for (const wheel of autoWheels) {
    [...wheel.children].forEach((row, index) => row.setAttribute("aria-selected", String(index === wheelIndex(wheel))));
  }
  const parts = [
    [wheelValue(autoHours), "小时"],
    [wheelValue(autoMinutes), "分钟"],
    [wheelValue(autoSeconds), "秒"],
  ].filter(([value]) => value).map(([value, unit]) => `${value} ${unit}`);
  const text = autoIntervalSeconds() < 10
    ? "间隔至少 10 秒。"
    : `每 ${parts.join(" ")} 发布一篇。`;
  document.getElementById("auto-interval-help").textContent = text;
}
let autoTimer = null;
function renderAutoStatus(data) {
  const running = data.status === "running";
  document.getElementById("auto-start").hidden = running;
  document.getElementById("auto-stop").hidden = !running;
  const progress = data.target ? `（${data.published}/${data.target}）` : (running ? `（已发 ${data.published} 篇）` : "");
  document.getElementById("auto-state").textContent = `${data.message || "未启动。"}${progress}`;
  const log = document.getElementById("auto-log");
  log.replaceChildren(...data.log.map(line => {
    const item = document.createElement("li");
    item.textContent = line;
    return item;
  }));
  clearTimeout(autoTimer);
  if (running) autoTimer = setTimeout(pollAutoStatus, 3000);
}
async function pollAutoStatus() {
  try {
    const response = await fetch("/api/auto/status", {cache:"no-store"});
    renderAutoStatus(await response.json());
  } catch (error) {
    document.getElementById("auto-state").textContent = `自动发布状态读取失败：${error.message}`;
  }
}
document.getElementById("show-publisher").addEventListener("click", () => {
  requestAnimationFrame(syncWheels);
  pollAutoStatus();
});
document.getElementById("auto-start").addEventListener("click", async () => {
  const folder = document.getElementById("auto-folder").value;
  const state = document.getElementById("auto-state");
  if (!folder) {
    state.textContent = "请先选择图片文件夹。";
    return;
  }
  if (autoIntervalSeconds() < 10) {
    state.textContent = "发布间隔至少 10 秒。";
    return;
  }
  const visibility = document.getElementById("auto-visibility").value;
  const target = Number(document.getElementById("auto-target").value) || 0;
  const folderText = folder === AUTO_RANDOM_FOLDER ? "每篇随机抽取" : folder;
  const confirmText = `确认开始全自动发布？\n文件夹：${folderText}\n可见范围：${visibility === "private" ? "仅自己可见" : "公开"}\n${document.getElementById("auto-interval-help").textContent}\n篇数：${target || "不限"}\n文案和图片不会再经过人工审核。`;
  if (!await askConfirm(confirmText, {okText:"开始发布"})) return;
  document.getElementById("auto-start").disabled = true;
  try {
    const response = await fetch("/api/auto/start", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        folder:folder === AUTO_RANDOM_FOLDER ? null : folder,
        count:Number(document.getElementById("auto-count").value),
        prompt:document.getElementById("auto-prompt").value,
        visibility,
        browser:document.getElementById("auto-browser").value,
        interval:autoIntervalSeconds(),
        target
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法启动自动发布");
    await pollAutoStatus();
  } catch (error) {
    state.textContent = `启动失败：${error.message}`;
  } finally {
    document.getElementById("auto-start").disabled = false;
  }
});
document.getElementById("auto-stop").addEventListener("click", async () => {
  try {
    const response = await fetch("/api/auto/stop", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "无法停止");
    await pollAutoStatus();
  } catch (error) {
    document.getElementById("auto-state").textContent = `停止失败：${error.message}`;
  }
});
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
    document.getElementById("publisher-state").textContent = `关闭小红书浏览器失败：${error.message}`;
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
    source: document.getElementById("search-source").value,
    threshold: Number(document.getElementById("threshold").value),
    target_count: Number(document.getElementById("target-count").value),
    output_dir: document.getElementById("output-dir").value.trim()
  };
  if (mode === "metrics" && selectedMetrics.length !== 1) {
    statusElement.textContent = "请选择一个外貌特征。";
    return;
  }
  if (mode === "metrics" && !payload.rewritten_queries) {
    statusElement.textContent = "请先点击“优化搜索词”，检查高/低搜索词结果后再开始收集。";
    return;
  }
  if (mode === "custom" && !payload.custom_topic) {
    statusElement.textContent = "请填写自定义搜索词。";
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


def validate_browser(browser: Any) -> str:
    if browser not in BROWSERS:
        raise ValueError("请选择有效的发布浏览器。")
    if browser not in installed_browsers():
        raise ValueError(f"本机没有安装 {BROWSERS[browser]['label']}，请换一个浏览器。")
    return browser


def validate_publisher_folder(mode: Any, folder: Any) -> Path:
    if mode not in {"comparison", "topic"}:
        raise ValueError("请选择有效的发布素材模式。")
    if not isinstance(folder, str) or not folder.strip() or len(folder) > 500:
        raise ValueError("请选择有效的图片文件夹。")
    requested_folder = ROOT / folder
    if requested_folder.is_symlink():
        raise ValueError("不能使用符号链接作为图片文件夹。")
    selected_folder = requested_folder.resolve()
    if (
        selected_folder.parent != ROOT
        or selected_folder.is_symlink()
        or not selected_folder.is_dir()
        or selected_folder.name.lower() in PROTECTED_DIRS
    ):
        raise ValueError("只能选择项目根目录中可访问的图片文件夹。")
    is_metric = selected_folder.name in METRIC_NAMES
    if (mode == "comparison") != is_metric:
        raise ValueError("所选图片文件夹与当前模式不匹配，请重新选择。")
    return selected_folder


def scan_publisher_folders() -> list[dict[str, Any]]:
    """列出可用于发布的图片文件夹；min_group_count 是每组（数值高/低或整个话题）最少的图片数。"""
    folders: list[dict[str, Any]] = []
    for folder in ROOT.iterdir():
        if not folder.is_dir() or folder.is_symlink() or folder.name.lower() in PROTECTED_DIRS:
            continue
        is_metric = folder.name in METRIC_NAMES
        if is_metric:
            high_dir = folder / "数值高"
            low_dir = folder / "数值低"
            if high_dir.is_symlink() or low_dir.is_symlink():
                continue
            high_count = count_managed_images(high_dir) if high_dir.is_dir() else 0
            low_count = count_managed_images(low_dir) if low_dir.is_dir() else 0
            if not high_count or not low_count:
                continue
            image_count = high_count + low_count
            min_group_count = min(high_count, low_count)
        else:
            image_count = count_managed_images(folder)
            if not image_count:
                continue
            min_group_count = image_count
        folders.append({
            "name": folder.name,
            "path": folder.name,
            "image_count": image_count,
            "min_group_count": min_group_count,
            "is_metric": is_metric,
        })
    return sorted(folders, key=lambda item: item["name"].casefold())


def folder_mode(name: str) -> str:
    """外貌特征文件夹按高低对比发布，其余按话题发布。"""
    return "comparison" if name in METRIC_NAMES else "topic"


def random_publisher_folder(count: int, previous: str | None = None) -> str:
    """每篇随机抽一个图片数量足够的文件夹；有多个可选时避免和上一篇重复。"""
    candidates = [
        folder["name"]
        for folder in scan_publisher_folders()
        if folder["min_group_count"] >= count
    ]
    if not candidates:
        raise RuntimeError(f"没有图片数量足够（每组至少 {count} 张）的文件夹可供随机抽取。")
    if len(candidates) > 1 and previous in candidates:
        candidates.remove(previous)
    return random.choice(candidates)


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


def run_crawler(command: list[str], api_key: str | None = None) -> None:
    with job_lock:
        job["status"] = "running"
    try:
        child_env = os.environ.copy()
        child_env.pop("HF_TOKEN", None)
        child_env.pop("HUGGINGFACEHUB_API_TOKEN", None)
        if api_key:
            child_env["MISTRAL_API_KEY"] = api_key
        else:
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
    visibility: str,
    auto_publish: bool,
    browser: str,
) -> None:
    global publisher_driver

    def update_status(message: str) -> None:
        with publisher_lock:
            publisher_state.update(status="starting", message=message)

    def register_driver(driver: Any) -> None:
        # 浏览器一启动就登记，状态轮询才能发现用户中途把它关掉了。
        global publisher_driver
        with publisher_lock:
            publisher_driver = driver

    try:
        driver = open_filled_draft(image_paths, title, content, visibility, update_status, register_driver, browser)
        if auto_publish:
            click_publish(driver, update_status)
    except PublisherEditorNotFound as exc:
        with publisher_lock:
            publisher_driver = exc.driver
            publisher_state.update(status="ready", message=str(exc))
        return
    except PublisherManualIntervention as exc:
        with publisher_lock:
            publisher_driver = exc.driver
            publisher_state.update(status="ready", message=str(exc))
        return
    except Exception as exc:
        with publisher_lock:
            driver = publisher_driver
            publisher_driver = None
        browser_closed = driver is not None and not browser_alive(driver)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        message = (
            "浏览器在处理中被关闭，本次未完成，可以重新点击。"
            if browser_closed
            else f"打开小红书草稿失败：{exc}"
        )
        with publisher_lock:
            publisher_state.update(status="error", message=message)
        return
    if auto_publish:
        try:
            driver.quit()
        except Exception:
            pass
        with publisher_lock:
            publisher_driver = None
            publisher_state.update(
                status="draft",
                message="已自动点击发布，小红书显示发布成功"
                + ("（仅自己可见）" if visibility == "private" else "")
                + "。",
            )
        return
    with publisher_lock:
        publisher_driver = driver
        publisher_state.update(
            status="ready",
            message=(
                "草稿已填入浏览器"
                + ("，可见范围已设为“仅自己可见”" if visibility == "private" else "，可见范围为公开")
                + "。请检查图片顺序、标题和正文，并手动点击发布。"
            ),
        )


def auto_log(message: str, **changes: Any) -> None:
    with publisher_lock:
        auto_state.update(message=message, **changes)
        auto_state["log"] = [f"{time.strftime('%H:%M:%S')} {message}", *auto_state["log"]][:50]


def run_auto_publisher(config: dict[str, Any]) -> None:
    """全自动循环：随机抽图 → 生成文案 → 填入草稿 → 点击发布 → 等待间隔。"""
    failures = 0
    published = 0
    target = config["target"]
    folder = None
    while not auto_stop_event.is_set():
        round_no = published + 1
        driver = None
        try:
            with job_lock:
                api_key = mistral_api_key
            if not api_key:
                raise RuntimeError("未绑定 Mistral API Key。")
            # folder 为 None 表示“每篇随机抽取一个文件夹”，每一轮都重新抽。
            folder = config["folder"] or random_publisher_folder(config["count"], folder)
            mode = folder_mode(folder)
            auto_log(f"第 {round_no} 篇：文件夹「{folder}」，正在抽图并生成文案。", next_at=None)
            images, _ = build_post_images(ROOT, mode, folder, config["count"])
            copy = generate_copywriting(api_key, mode, folder, config["prompt"])
            auto_log(f"第 {round_no} 篇：文案《{copy['title']}》已生成，正在打开小红书。")

            def update_status(message: str) -> None:
                if "无反应" in message:
                    auto_log(f"第 {round_no} 篇：{message}")
                    return
                with publisher_lock:
                    auto_state["message"] = f"第 {round_no} 篇：{message}"

            driver = open_filled_draft(
                images, copy["title"], copy["content"], config["visibility"], update_status, browser=config["browser"]
            )
            click_publish(driver, update_status)
            published += 1
            failures = 0
            auto_log(f"第 {round_no} 篇《{copy['title']}》已发布。", published=published)
        except Exception as exc:
            failures += 1
            # 草稿步骤失败时浏览器挂在异常上，也要关掉，否则下一轮无法复用同一个浏览器配置目录。
            driver = driver or getattr(exc, "driver", None)
            auto_log(f"第 {round_no} 篇失败（连续 {failures} 次）：{exc}")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

        if target and published >= target:
            auto_log(f"已完成全部 {target} 篇，自动发布结束。", status="idle", next_at=None)
            return
        if failures >= AUTO_MAX_CONSECUTIVE_FAILURES:
            auto_log("连续失败次数过多，已停止自动发布，请检查登录状态和素材。", status="error", next_at=None)
            return
        next_at = time.time() + config["interval"]
        with publisher_lock:
            auto_state["next_at"] = next_at
            auto_state["message"] = f"已发布 {published} 篇，等待下一篇（{time.strftime('%H:%M:%S', time.localtime(next_at))}）。"
        if auto_stop_event.wait(config["interval"]):
            break
    auto_log(f"已手动停止自动发布，共发布 {published} 篇。", status="idle", next_at=None)


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
        if request.path == "/api/publisher/candidates":
            query = parse_qs(request.query)
            self.list_publisher_candidates(query.get("mode", [""])[0], query.get("folder", [""])[0])
            return
        if request.path == "/api/publisher/candidate-image":
            query = parse_qs(request.query)
            self.send_publisher_candidate_image(
                query.get("mode", [""])[0],
                query.get("folder", [""])[0],
                query.get("path", [""])[0],
            )
            return
        if request.path == "/api/auto/status":
            with publisher_lock:
                snapshot = {**auto_state, "log": list(auto_state["log"])}
            self.send_json(snapshot)
            return
        if request.path == "/api/publisher/status":
            self.send_publisher_status()
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
        if self.path in {"/api/auto/start", "/api/auto/stop"}:
            if not self.is_same_origin_request():
                self.send_json({"error": "自动发布请求只允许来自当前本机网页。"}, 403)
                return
            if self.path == "/api/auto/start":
                self.start_auto_publisher()
            else:
                self.stop_auto_publisher()
            return
        if self.path in {"/api/publisher/prepare", "/api/publisher/launch", "/api/publisher/close"}:
            if not self.is_same_origin_request():
                self.send_json({"error": "小红书助手请求只允许来自当前本机网页。"}, 403)
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
            current_api_key = mistral_api_key

        worker = threading.Thread(target=run_crawler, args=(command, current_api_key), daemon=True)
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
        try:
            folders = scan_publisher_folders()
        except OSError as exc:
            self.send_json({"error": f"读取图片文件夹失败：{exc}"}, 500)
            return
        self.send_json({"folders": folders, "browsers": installed_browsers()})

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
                raise ValueError("请选择有效的图片文件夹。")
            if isinstance(count, bool) or not isinstance(count, int):
                raise ValueError("挑选数量必须是整数。")
            if not isinstance(prompt, str) or len(prompt) > 2000:
                raise ValueError("创作者 Prompt 不能超过 2000 个字符。")
            selected_images = payload.get("selected")
            if selected_images is not None and (
                not isinstance(selected_images, list)
                or not all(isinstance(item, str) for item in selected_images)
            ):
                raise ValueError("手动选图列表格式错误。")
            selected_folder = validate_publisher_folder(mode, folder)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return

        with publisher_lock:
            if publisher_state["status"] == "generating":
                self.send_json({"error": "当前正在生成草稿，请稍候。"}, 409)
                return
            publisher_draft = None
            publisher_state.update(status="generating", message="正在抽取素材并生成文案。")
        with job_lock:
            api_key = mistral_api_key
        if not api_key:
            with publisher_lock:
                publisher_state.update(status="error", message="请先绑定 密钥 (API Key)。")
            self.send_json({"error": "请先在收集面板绑定 密钥 (API Key)。"}, 400)
            return

        try:
            images, _ = build_post_images(ROOT, mode, folder, count, selected_images)
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
        self.send_image_file(image_path, "no-store")

    def send_image_file(self, image_path: Path, cache_control: str) -> None:
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
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def start_auto_publisher(self) -> None:
        try:
            payload = self.read_json_body()
            folder = payload.get("folder")
            random_folder = folder is None
            if not random_folder:
                if not isinstance(folder, str):
                    raise ValueError("请选择有效的图片文件夹。")
                selected_folder = validate_publisher_folder(folder_mode(folder), folder)
            count = payload.get("count")
            prompt = payload.get("prompt", "")
            visibility = payload.get("visibility", "public")
            browser = validate_browser(payload.get("browser", DEFAULT_BROWSER))
            interval = payload.get("interval")
            target = payload.get("target", 0)
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
                raise ValueError("每篇挑选数量需在 1 到 8 之间。")
            if not isinstance(prompt, str) or len(prompt) > 2000:
                raise ValueError("创作者 Prompt 不能超过 2000 个字符。")
            if visibility not in {"public", "private"}:
                raise ValueError("可见范围只能是 public 或 private。")
            if isinstance(interval, bool) or not isinstance(interval, int) or not AUTO_MIN_INTERVAL_SECONDS <= interval <= 24 * 3600:
                raise ValueError("发布间隔需在 10 秒到 24 小时之间。")
            if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target <= 100:
                raise ValueError("发布篇数需在 0（不限）到 100 之间。")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        with publisher_lock:
            if auto_state["status"] == "running":
                self.send_json({"error": "自动发布已在运行中。"}, 409)
                return
            if publisher_driver is not None or publisher_state["status"] in {"starting", "closing"}:
                self.send_json({"error": "请先关闭手动流程打开的小红书浏览器，再启动自动发布。"}, 409)
                return
            auto_stop_event.clear()
            auto_state.update(status="running", published=0, target=target, next_at=None, log=[])
        config = {
            "folder": None if random_folder else selected_folder.name,
            "count": count,
            "prompt": prompt,
            "visibility": visibility,
            "browser": browser,
            "interval": interval,
            "target": target,
        }
        auto_log("自动发布已启动。")
        threading.Thread(target=run_auto_publisher, args=(config,), daemon=True).start()
        self.send_json({"status": "running"}, 202)

    def stop_auto_publisher(self) -> None:
        with publisher_lock:
            running = auto_state["status"] == "running"
            if running:
                auto_state["message"] = "正在停止：当前这篇处理完后结束。"
        auto_stop_event.set()
        self.send_json({"status": "stopping" if running else "idle"})

    def list_publisher_candidates(self, mode: str, folder: str) -> None:
        try:
            selected_folder = validate_publisher_folder(mode, folder)
            groups = list_candidate_images(ROOT, mode, folder)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        except OSError as exc:
            self.send_json({"error": f"读取图片列表失败：{exc}"}, 500)
            return
        self.send_json({
            "groups": [
                {
                    "name": name,
                    "images": [
                        {"path": candidate_key(selected_folder, path), "name": path.name}
                        for path in images
                    ],
                }
                for name, images in groups.items()
            ],
        })

    def send_publisher_candidate_image(self, mode: str, folder: str, key: str) -> None:
        try:
            selected_folder = validate_publisher_folder(mode, folder)
            groups = list_candidate_images(ROOT, mode, folder)
        except (ValueError, OSError) as exc:
            self.send_json({"error": str(exc)}, 400)
            return
        # 只返回候选列表里的图片，避免通过 path 参数读取任意文件。
        for images in groups.values():
            for path in images:
                if candidate_key(selected_folder, path) == key:
                    self.send_image_file(path, "private, max-age=300")
                    return
        self.send_json({"error": "图片不存在。"}, 404)

    def send_publisher_status(self) -> None:
        global publisher_driver
        with publisher_lock:
            driver = publisher_driver if publisher_state["status"] == "ready" else None
        if driver is not None and not browser_alive(driver):
            try:
                driver.quit()
            except Exception:
                pass
            with publisher_lock:
                if publisher_driver is driver:
                    publisher_driver = None
                    publisher_state.update(status="draft", message="小红书浏览器已被关闭，可以重新打开。")
        with publisher_lock:
            status = dict(publisher_state)
        self.send_json(status)

    def launch_publisher_draft(self) -> None:
        global publisher_driver
        try:
            payload = self.read_json_body()
            title = payload.get("title")
            content = payload.get("content")
            visibility = payload.get("visibility", "public")
            auto_publish = payload.get("auto_publish", False)
            browser = validate_browser(payload.get("browser", DEFAULT_BROWSER))
            if visibility not in {"public", "private"}:
                raise ValueError("可见范围只能是 public 或 private。")
            if not isinstance(auto_publish, bool):
                raise ValueError("自动发布选项格式错误。")
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
            if publisher_state["status"] in {"generating", "starting", "closing"}:
                self.send_json({"error": "当前小红书草稿正在处理中。"}, 409)
                return
            if auto_state["status"] == "running":
                self.send_json({"error": "自动发布运行中，会占用小红书浏览器；请先停止自动发布。"}, 409)
                return
            publisher_draft["copy"] = {"title": title.strip(), "content": content.strip()}
            image_paths = list(publisher_draft["images"])
            old_driver = publisher_driver
            publisher_driver = None
            publisher_state.update(status="starting", message="正在启动小红书创作者编辑页。")
        if old_driver is not None:
            try:
                old_driver.quit()
            except Exception:
                pass
        worker = threading.Thread(
            target=run_publisher_browser,
            args=(image_paths, title.strip(), content.strip(), visibility, auto_publish, browser),
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
                self.send_json({"error": "抓取任务运行期间不能优化搜索词。"}, 409)
                return
            api_key = mistral_api_key
        if api_key is None:
            self.send_json({"error": "请先绑定 密钥 (API Key)。"}, 400)
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
                    raise ValueError("请输入有效的 密钥 (API Key)。")
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
        source = payload.get("source", "looksmax")
        if source not in {"looksmax", "bing", "baidu", "so360"}:
            raise ValueError("请选择有效的图片搜索来源。")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0.35 <= threshold <= 0.95:
            raise ValueError("CLIP 严格度必须在 0.35 到 0.95 之间。")
        if isinstance(target_count, bool) or not isinstance(target_count, int) or not 1 <= target_count <= 1000:
            raise ValueError("每个分类需要的图片数量必须在 1 到 1000 之间。")
        if not isinstance(output_dir, str) or not output_dir.strip() or len(output_dir) > 1000:
            raise ValueError("请填写有效的图片保存目录。")

        command = [
            sys.executable,
            str(SCRAPER),
            "--target-count",
            str(target_count),
            "--clip-threshold",
            f"{threshold:.2f}",
            "--source",
            source,
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
                raise ValueError("自定义搜索词不能为空，且不能超过 240 个字符。")
            command.extend(["--custom-topic", topic.strip()])
        else:
            metrics = payload.get("metrics")
            if not isinstance(metrics, list) or len(metrics) != 1:
                raise ValueError("请选择一个外貌特征。")
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
    print(f"图片收集小助手已启动：http://127.0.0.1:{port}")
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