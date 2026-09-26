"""Local web interface for configuring and running the image crawler."""

from __future__ import annotations

import ast
import html
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SCRAPER = ROOT / "自动抓取脚本.py"
DEFAULT_OUTPUT = ROOT / "抓取结果"
MAX_REQUEST_BYTES = 64 * 1024
job_lock = threading.Lock()
job: dict[str, Any] = {
    "status": "idle",
    "logs": [],
    "returncode": None,
    "error": None,
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
    [hidden] { display:none!important; }
    @media(max-width:700px) { .topbar { padding:0 18px; } main { padding:42px 18px 56px; } .hero { grid-template-columns:1fr; gap:12px; padding-bottom:28px; } .hero-copy { max-width:none; } .grid { grid-template-columns:1fr; gap:0; } .panel { padding:20px 18px; } .brand { gap:8px; } .brand img { width:42px; height:39px; } }
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
  <form id="crawl-form">
    <section class="panel">
      <h2>1. 选择抓取内容</h2>
      <div class="mode">
        <label><input type="radio" name="mode" value="metrics" checked> 手动选择 63 项指标</label>
        <label><input type="radio" name="mode" value="random_mistral"> 随机抽 1 项 + Mistral 7B 改写</label>
        <label><input type="radio" name="mode" value="custom"> 自定义搜索话题</label>
      </div>
      <div id="metric-section" class="field">
        <div class="toolbar">
          <input id="metric-filter" type="text" placeholder="搜索指标名称">
          <button type="button" id="select-all">全选</button>
          <button type="button" id="clear-all">清空</button>
          <span class="help" id="selected-count"></span>
        </div>
        <div id="metrics" aria-label="指标列表"></div>
        <p class="help" id="metric-help">可选择一个或多个指标；每个指标包含脚本中定义的 high / low 搜索词。</p>
      </div>
      <div id="random-section" class="field" hidden>
        <p class="help">启动后会从全部 63 项中随机抽取一项，将其 high / low 搜索词分别交给 Mistral 7B 改写，再用于 Bing 图片搜索。需要 Hugging Face Token；请在启动网页的 PowerShell 中设置 <code>HF_TOKEN</code>。令牌不在网页中显示或写入任务日志。</p>
        <p class="help">模型：mistralai/Mistral-7B-Instruct-v0.3（通过 Hugging Face Inference Providers 托管调用）</p>
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
          <p class="help">默认保存在项目根目录下的“抓取结果”文件夹。分类子文件夹会创建在该目录内；相对路径以项目根目录为基准。</p>
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
</main>
<script>
const metricsRoot = document.getElementById("metrics");
const form = document.getElementById("crawl-form");
const startButton = document.getElementById("start");
const statusElement = document.getElementById("status");
const logsElement = document.getElementById("logs");
const metricFilter = document.getElementById("metric-filter");
let timer = null;

function updateMode() {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const manual = mode === "metrics";
  const metricSection = document.getElementById("metric-section");
  metricSection.hidden = mode === "custom";
  metricsRoot.querySelectorAll("input").forEach(item => { item.disabled = !manual; });
  document.getElementById("metric-filter").disabled = !manual;
  document.getElementById("select-all").disabled = !manual;
  document.getElementById("clear-all").disabled = !manual;
  document.getElementById("metric-help").textContent = manual
    ? "可选择一个或多个指标；每个指标包含脚本中定义的 high / low 搜索词。"
    : "列表仅供查看；抓取时会忽略手动勾选，并从全部 63 项中随机抽取一项。";
  document.getElementById("random-section").hidden = mode !== "random_mistral";
  document.getElementById("custom-section").hidden = mode !== "custom";
}
function updateCount() {
  const count = metricsRoot.querySelectorAll("input:checked").length;
  document.getElementById("selected-count").textContent = `已选 ${count} 项`;
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
    checkbox.type = "checkbox";
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
document.querySelectorAll('input[name="mode"]').forEach(item => item.addEventListener("change", updateMode));
document.getElementById("threshold").addEventListener("input", updateThreshold);
metricFilter.addEventListener("input", filterMetrics);
document.getElementById("select-all").addEventListener("click", () => {
  metricsRoot.querySelectorAll("input").forEach(item => { if (!item.closest("label").hidden) item.checked = true; });
  updateCount();
});
document.getElementById("clear-all").addEventListener("click", () => {
  metricsRoot.querySelectorAll("input").forEach(item => { item.checked = false; });
  updateCount();
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
form.addEventListener("submit", async event => {
  event.preventDefault();
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const selectedMetrics = [...metricsRoot.querySelectorAll("input:checked")].map(item => item.value);
  const payload = {
    mode,
    metrics: selectedMetrics,
    custom_topic: document.getElementById("custom-topic").value.trim(),
    threshold: Number(document.getElementById("threshold").value),
    target_count: Number(document.getElementById("target-count").value),
    output_dir: document.getElementById("output-dir").value.trim()
  };
  if (mode === "metrics" && selectedMetrics.length === 0) {
    statusElement.textContent = "请至少选择一个指标。";
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


def run_crawler(command: list[str]) -> None:
    with job_lock:
        job["status"] = "running"
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
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
        if self.path == "/":
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
        if self.path == "/api/metrics":
            self.send_json(METRIC_NAMES)
            return
        if self.path == "/api/status":
            with job_lock:
                snapshot = {
                    **job,
                    "logs": "\n".join(job["logs"]),
                }
            self.send_json(snapshot)
            return
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
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

    def make_command(self, payload: Any) -> list[str]:
        if not isinstance(payload, dict):
            raise ValueError("请求格式错误。")
        mode = payload.get("mode")
        threshold = payload.get("threshold")
        target_count = payload.get("target_count")
        output_dir = payload.get("output_dir") or DEFAULT_OUTPUT
        if mode not in {"metrics", "random_mistral", "custom"}:
            raise ValueError("请选择手动指标、Mistral 随机抽取或自定义话题模式。")
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
        if mode == "random_mistral":
            command.append("--random-mistral")
        elif mode == "custom":
            topic = payload.get("custom_topic")
            if not isinstance(topic, str) or not topic.strip() or len(topic) > 240:
                raise ValueError("自定义搜索话题不能为空，且不能超过 240 个字符。")
            command.extend(["--custom-topic", topic.strip()])
        else:
            metrics = payload.get("metrics")
            if not isinstance(metrics, list) or not metrics:
                raise ValueError("请至少选择一个指标。")
            if not all(isinstance(name, str) and name in METRIC_NAMES for name in metrics):
                raise ValueError("指标列表包含无效选项，请刷新页面后重试。")
            for name in dict.fromkeys(metrics):
                command.extend(["--metric", name])
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


if __name__ == "__main__":
    main()
