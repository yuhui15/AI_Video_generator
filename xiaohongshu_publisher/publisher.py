from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import os
import shutil

import psutil
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
PUBLISHER_DIR = Path(__file__).resolve().parent
CHROME_START_TIMEOUT = 90
DEFAULT_BROWSER = "edge"
_PROGRAM_FILES = [os.environ.get("PROGRAMFILES", r"C:\Program Files"), os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), os.environ.get("LOCALAPPDATA", "")]
# 每种浏览器使用独立的登录目录（Chrome 沿用原来的 .browser_profile，已登录状态不丢）
BROWSERS = {
    "edge": {
        "label": "Microsoft Edge",
        "profile": PUBLISHER_DIR / ".browser_profile_edge",
        "process": "msedge",
        "exe": [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for base in _PROGRAM_FILES if base],
    },
    "chrome": {
        "label": "Google Chrome",
        "profile": PUBLISHER_DIR / ".browser_profile",
        "process": "chrome",
        "exe": [Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe" for base in _PROGRAM_FILES if base],
    },
    "firefox": {
        "label": "Firefox",
        "profile": PUBLISHER_DIR / ".browser_profile_firefox",
        "process": "firefox",
        "exe": [Path(base) / "Mozilla Firefox" / "firefox.exe" for base in _PROGRAM_FILES if base],
    },
}
PROFILE_DIR = BROWSERS["chrome"]["profile"]   # 兼容旧代码


class PublisherEditorNotFound(RuntimeError):
    def __init__(self, driver: uc.Chrome, message: str) -> None:
        super().__init__(message)
        self.driver = driver


class PublisherManualIntervention(RuntimeError):
    def __init__(self, driver: uc.Chrome, message: str) -> None:
        super().__init__(message)
        self.driver = driver


def open_filled_draft(
    image_paths: list[Path],
    title: str,
    content: str,
    visibility: str,
    status_callback: Callable[[str], None],
    driver_callback: Callable[[uc.Chrome], None] | None = None,
    browser: str = DEFAULT_BROWSER,
) -> uc.Chrome:
    status_callback(f"正在启动 {BROWSERS[browser]['label']}。")
    driver = _start_browser(browser)
    # 用户中途关掉浏览器时，页面加载不能一直卡着（默认 300 秒）。
    driver.set_page_load_timeout(60)
    if driver_callback is not None:
        driver_callback(driver)

    try:
        status_callback("正在打开小红书创作者平台；如未登录，请在浏览器中完成登录。")
        driver.get(CREATOR_URL)
        wait = WebDriverWait(driver, 180)
        
        status_callback("正在检查小红书“上传图文”页面状态。")
        try:
            WebDriverWait(driver, 45).until(lambda d: _click_upload_image_mode(d))
        except TimeoutException as exc:
            raise PublisherManualIntervention(
                driver,
                _describe_missing_upload_tab(driver),
            ) from exc

        try:
            status_callback("正在定位图片上传控件。")
            file_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input.upload-input[type="file"]'))
            )
        except TimeoutException as exc:
            raise PublisherManualIntervention(
                driver,
                "已进入页面，但未找到图片文件上传控件。"
                "请检查登录状态或页面提示；浏览器会保持打开。",
            ) from exc
            
        _upload_images(driver, file_input, image_paths)
        status_callback("图片已成功注入上传，正在等待标题与正文编辑器加载。")

        try:
            # 1. 填写标题
            title_input = wait.until(
                lambda browser: _first_visible(
                    browser,
                    (
                        (By.CSS_SELECTOR, 'input[placeholder*="标题"]'),
                        (By.CSS_SELECTOR, 'input[placeholder*="填写标题"]'),
                        (By.CSS_SELECTOR, 'input.el-input__inner'),
                        (By.CSS_SELECTOR, '.publish-title input'),
                    ),
                )
            )
            driver.execute_script("""
                arguments[0].focus();
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """, title_input, title)

            # 2. 填写正文（分行与段落完美保留）
            editor = wait.until(
                lambda browser: _first_visible(
                    browser,
                    (
                        (By.CSS_SELECTOR, '[contenteditable="true"]'),
                        (By.CSS_SELECTOR, ".ProseMirror"),
                        (By.CSS_SELECTOR, "textarea[placeholder*='正文']"),
                        (By.CSS_SELECTOR, "textarea[placeholder*='描述']"),
                    ),
                )
            )
            driver.execute_script("""
                arguments[0].focus();
                const text = arguments[1];
                const paragraphs = text.split('\\n');
                const htmlContent = paragraphs.map(p => `<p>${p === '' ? '<br>' : p}</p>`).join('');
                arguments[0].innerHTML = htmlContent;
                
                const dt = new DataTransfer();
                dt.setData('text/plain', text);
                const pasteEvent = new ClipboardEvent('paste', {
                    clipboardData: dt,
                    bubbles: true,
                    cancelable: true
                });
                arguments[0].dispatchEvent(pasteEvent);
                arguments[0].dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertParagraph' }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            """, editor, content)
            
        except TimeoutException as exc:
            raise PublisherEditorNotFound(
                driver,
                _describe_missing_editor(driver),
            ) from exc

        if visibility == "private":
            status_callback("正在将可见范围设置为“仅自己可见”。")
            try:
                WebDriverWait(driver, 20).until(lambda d: _set_private_visibility(d))
            except TimeoutException as exc:
                raise PublisherManualIntervention(
                    driver,
                    "草稿已填入，但未能自动把可见范围设为“仅自己可见”。"
                    "请在页面底部的权限/可见范围设置中手动选择“仅自己可见”后再发布。",
                ) from exc

        status_callback(
            "草稿已成功填入浏览器！请检查图片顺序、标题和正文，并在小红书页面手动点击发布。"
        )
        return driver
    except PublisherEditorNotFound:
        raise
    except PublisherManualIntervention:
        raise
    except Exception as exc:
        raise RuntimeError(f"草稿准备失败：{exc}") from exc


def installed_browsers() -> list[str]:
    """返回本机已安装、可用于发布的浏览器。"""
    found = []
    for key, info in BROWSERS.items():
        if any(path.is_file() for path in info["exe"]) or shutil.which(f"{info['process']}.exe"):
            found.append(key)
    return found


def _start_browser(browser: str):
    if browser not in BROWSERS:
        raise RuntimeError(f"不支持的浏览器：{browser}")
    if browser not in installed_browsers():
        raise RuntimeError(f"本机没有安装 {BROWSERS[browser]['label']}，请换一个浏览器或先安装它。")
    # 上次残留的专用浏览器会占着配置目录，新浏览器启动时会无限等待，先清掉。
    close_stale_browsers(browser)
    box: dict[str, object] = {}

    def start() -> None:
        try:
            if browser == "chrome":
                try:
                    box["driver"] = uc.Chrome(options=_chrome_options(), version_main=153)
                except Exception:
                    # uc 不允许复用同一个 ChromeOptions，重试时必须新建。
                    box["driver"] = uc.Chrome(options=_chrome_options())
            elif browser == "edge":
                driver = webdriver.Edge(options=_edge_options())
                # 隐藏 navigator.webdriver，减少被识别为自动化浏览器
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
                )
                box["driver"] = driver
            else:
                driver = webdriver.Firefox(options=_firefox_options())
                driver.maximize_window()
                box["driver"] = driver
        except BaseException as exc:
            box["error"] = exc

    worker = threading.Thread(target=start, daemon=True)
    worker.start()
    worker.join(CHROME_START_TIMEOUT)
    if worker.is_alive():
        close_stale_browsers(browser)
        raise RuntimeError("浏览器启动超时（可能在启动过程中被关闭），请重新点击。")
    if "error" in box:
        raise RuntimeError(f"浏览器启动失败：{box['error']}")
    return box["driver"]  # type: ignore[return-value]


def close_stale_browsers(browser: str | None = None) -> None:
    """结束使用本工具专用登录目录的浏览器进程（不影响你日常使用的浏览器）。

    browser 为 None 时清理所有浏览器的专用目录。
    """
    targets = [browser] if browser else list(BROWSERS)
    rules = [(BROWSERS[key]["process"], str(BROWSERS[key]["profile"]).lower()) for key in targets]
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (process.info["name"] or "").lower()
            cmdline = " ".join(process.info["cmdline"] or []).lower()
            for prefix, profile in rules:
                # Chrome/Edge 用 --user-data-dir=目录，Firefox 用 -profile 目录
                if name.startswith(prefix) and (f"--user-data-dir={profile}" in cmdline or f"-profile {profile}" in cmdline):
                    process.kill()
                    break
        except psutil.Error:
            continue


def _chrome_options() -> uc.ChromeOptions:
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={BROWSERS['chrome']['profile']}")
    options.add_argument("--start-maximized")
    return options


def _edge_options() -> webdriver.EdgeOptions:
    options = webdriver.EdgeOptions()
    options.add_argument(f"--user-data-dir={BROWSERS['edge']['profile']}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def _firefox_options() -> webdriver.FirefoxOptions:
    profile = BROWSERS["firefox"]["profile"]
    profile.mkdir(parents=True, exist_ok=True)
    options = webdriver.FirefoxOptions()
    options.add_argument("-profile")
    options.add_argument(str(profile))
    options.set_preference("dom.webdriver.enabled", False)
    return options


def _is_chromium(driver) -> bool:
    return str(driver.capabilities.get("browserName", "")).lower() in {"chrome", "msedge", "microsoftedge"}


def browser_alive(driver: uc.Chrome) -> bool:
    try:
        return bool(driver.window_handles)
    except Exception:
        return False


def _upload_images(driver: uc.Chrome, file_input, image_paths: list[Path]) -> None:
    if not image_paths:
        raise ValueError("没有可上传的图片。")
    
    resolved_paths = [str(path.resolve()) for path in image_paths if path.is_file()]
    if not resolved_paths:
        raise ValueError("找不到任何有效的图片文件用于上传。")

    driver.execute_script("""
        arguments[0].style.display = 'block';
        arguments[0].style.visibility = 'visible';
        arguments[0].style.opacity = '1';
        arguments[0].style.position = 'absolute';
        arguments[0].style.left = '0px';
        arguments[0].style.top = '0px';
        arguments[0].style.zIndex = '999999';
        if (arguments[0].getAttribute('multiple') === null) {
            arguments[0].setAttribute('multiple', 'true');
        }
    """, file_input)

    time.sleep(0.5)
    file_input.send_keys("\n".join(resolved_paths))
    time.sleep(1)


def _click_upload_image_mode(driver: uc.Chrome) -> bool:
    xpath = "//div[contains(@class, 'creator-tab') and not(contains(@style, '-9999px')) and .//span[normalize-space(text())='上传图文']]"
    elements = driver.find_elements(By.XPATH, xpath)
    
    if not elements:
        elements = driver.find_elements(By.XPATH, "//*[normalize-space(text())='上传图文']")

    for element in elements:
        if element.is_displayed():
            try:
                element.click()
                return True
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                    return True
                except Exception:
                    continue
    return False


PUBLISH_HOST_SELECTOR = "xhs-publish-btn"
# “发布”按钮在 <xhs-publish-btn> 的 closed shadow root 里，DOM 查询拿不到。
# 里面是两个 120px 宽、间距 24px 的居中按钮，“发布”在右边，所以中心点在宿主中心右侧 72px。
PUBLISH_BUTTON_OFFSET_X = 60 + 24 / 2
PUBLISH_CLICK_ATTEMPTS = 3
PUBLISH_REACTION_SECONDS = 10


def click_publish(driver: uc.Chrome, status_callback: Callable[[str], None]) -> None:
    """等图片上传完成后点击“发布”，并等待发布成功的信号。"""
    status_callback("正在等待图片上传完成。")
    WebDriverWait(driver, 180).until(
        lambda d: not any(
            element.is_displayed()
            for element in d.find_elements(By.XPATH, "//*[contains(text(), '上传中')]")
        )
    )
    try:
        host = WebDriverWait(driver, 60).until(_ready_publish_host)
    except TimeoutException as exc:
        raise RuntimeError("“发布”按钮一直不可用（可能图片仍在处理或页面有未填项）。") from exc
    time.sleep(2)
    x, y = driver.execute_script(
        "const r = arguments[0].getBoundingClientRect();"
        "return [r.left + r.width / 2 + arguments[1], r.top + r.height / 2];",
        host,
        PUBLISH_BUTTON_OFFSET_X,
    )
    # 点击前先确认该坐标下确实是红色“发布”按钮，避免页面改版后点错（比如点到“暂存离开”）。
    if _is_chromium(driver):
        target = _describe_node_at(driver, x, y)
        if target.get("nodeName") != "BUTTON" or "bg-red" not in target.get("class", ""):
            raise RuntimeError(f"“发布”按钮位置与预期不符（该位置是 {target or '空'}），已停止，未点击。")
    else:
        # Firefox 没有 CDP，看不到封闭 Shadow DOM 内部；至少确认坐标落在发布按钮组件上
        on_host = driver.execute_script(
            "const el = document.elementFromPoint(arguments[0], arguments[1]);"
            "return !!el && el.tagName.toLowerCase() === arguments[2];",
            x, y, PUBLISH_HOST_SELECTOR,
        )
        if not on_host:
            raise RuntimeError("“发布”按钮位置与预期不符，已停止，未点击。")
    # 偶尔点击后页面毫无反应（按钮没进入 loading），所以没反应时重点；一旦开始发布就只等待，绝不重复点击。
    for attempt in range(1, PUBLISH_CLICK_ATTEMPTS + 1):
        status_callback("正在点击“发布”。" if attempt == 1 else f"点击后无反应，第 {attempt} 次点击“发布”。")
        _click_at(driver, x, y)
        if _wait_publish_started(driver, PUBLISH_REACTION_SECONDS):
            break
    else:
        raise RuntimeError(f"连续点击“发布” {PUBLISH_CLICK_ATTEMPTS} 次都没有反应，请到小红书页面检查。")
    try:
        WebDriverWait(driver, 60).until(_publish_finished)
    except TimeoutException as exc:
        raise RuntimeError("已点击“发布”，但 60 秒内未看到发布成功提示，请到小红书检查。") from exc


def _click_at(driver, x: float, y: float) -> None:
    """在视口坐标处发送真实鼠标点击（能点到封闭 Shadow DOM 里的按钮）。"""
    if _is_chromium(driver):
        for event in ("mouseMoved", "mousePressed", "mouseReleased"):
            driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {"type": event, "x": x, "y": y, "button": "left", "clickCount": 1},
            )
        return
    actions = ActionBuilder(driver)
    actions.pointer_action.move_to_location(int(x), int(y))
    actions.pointer_action.click()
    actions.perform()


def _wait_publish_started(driver: uc.Chrome, seconds: float) -> bool:
    """点击后等待发布开始：按钮进入 loading、跳到成功页或发布按钮消失都算。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _publish_finished(driver):
            return True
        hosts = driver.find_elements(By.CSS_SELECTOR, PUBLISH_HOST_SELECTOR)
        if hosts and hosts[0].get_attribute("submit-loading") == "true":
            return True
        time.sleep(0.3)
    return False


def _ready_publish_host(driver: uc.Chrome):
    for host in driver.find_elements(By.CSS_SELECTOR, PUBLISH_HOST_SELECTOR):
        if (
            host.is_displayed()
            and host.get_attribute("submit-disabled") != "true"
            and host.get_attribute("submit-loading") != "true"
        ):
            return host
    return False


def _describe_node_at(driver: uc.Chrome, x: float, y: float) -> dict[str, str]:
    """用 CDP 查坐标处的真实节点（能穿透 closed shadow root）。"""
    driver.execute_cdp_cmd("DOM.getDocument", {"depth": 0})
    located = driver.execute_cdp_cmd(
        "DOM.getNodeForLocation",
        {"x": round(x), "y": round(y), "includeUserAgentShadowDOM": False},
    )
    node = driver.execute_cdp_cmd("DOM.describeNode", {"backendNodeId": located["backendNodeId"]})["node"]
    attributes = node.get("attributes", [])
    return {
        "nodeName": node.get("nodeName", ""),
        **{attributes[i]: attributes[i + 1] for i in range(0, len(attributes) - 1, 2)},
    }


def _publish_finished(driver: uc.Chrome) -> bool:
    url = driver.current_url
    if "/publish/success" in url or "published=true" in url or _visible_text_elements(driver, "发布成功"):
        return True
    # 发布成功后会离开编辑页，发布按钮随之消失。
    return not driver.find_elements(By.CSS_SELECTOR, PUBLISH_HOST_SELECTOR)


PRIVATE_LABEL = "仅自己可见"
PUBLIC_LABEL = "公开可见"


def _set_private_visibility(driver: uc.Chrome) -> bool:
    # 下拉框收起时只显示当前值；已是“仅自己可见”即完成。
    if _visible_text_elements(driver, PRIVATE_LABEL) and not _visible_text_elements(driver, PUBLIC_LABEL):
        return True
    # 单选/已展开的下拉：直接点“仅自己可见”。
    for element in _visible_text_elements(driver, PRIVATE_LABEL):
        if _safe_click(driver, element):
            time.sleep(0.5)
            if not _visible_text_elements(driver, PUBLIC_LABEL) or _looks_selected(element):
                return True
    # 收起的下拉：先点当前值“公开可见”展开选项。
    for element in _visible_text_elements(driver, PUBLIC_LABEL):
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        if _safe_click(driver, element):
            time.sleep(0.5)
            break
    return False


def _visible_text_elements(driver: uc.Chrome, text: str) -> list:
    xpath = f"//*[normalize-space(text())='{text}']"
    return [element for element in driver.find_elements(By.XPATH, xpath) if element.is_displayed()]


def _looks_selected(element) -> bool:
    try:
        marked = element.find_elements(
            By.XPATH,
            "./ancestor-or-self::*[position() <= 4][contains(@class, 'checked') "
            "or contains(@class, 'active') or contains(@class, 'selected') or @aria-checked='true']",
        )
        return bool(marked)
    except Exception:
        return False


def _safe_click(driver: uc.Chrome, element) -> bool:
    try:
        element.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False


def _describe_missing_upload_tab(driver: uc.Chrome) -> str:
    try:
        page_url = driver.current_url
        page_title = driver.title
    except Exception as exc:
        return f"无法定位图片上传控件，且读取页面状态失败：{exc}"
    return (
        "页面已打开，但未找到图片文件上传控件。"
        f"当前页面：{page_url}（{page_title}）。"
        "请确认已完成扫码登录；如果卡在登录页，请先在浏览器中手动登录。"
    )


def _first_visible(driver, locators):
    for by, selector in locators:
        for element in driver.find_elements(by, selector):
            if element.is_displayed():
                return element
    for by, selector in locators:
        for element in driver.find_elements(by, selector):
            return element
    return False


def _describe_missing_editor(driver: uc.Chrome) -> str:
    try:
        page_url = driver.current_url
        page_title = driver.title
        title_inputs = [
            element.get_attribute("placeholder") or element.get_attribute("aria-label") or "(无提示)"
            for element in driver.find_elements(By.CSS_SELECTOR, "input")
            if element.is_displayed()
        ]
        textareas = [
            element.get_attribute("placeholder") or element.get_attribute("aria-label") or "(无提示)"
            for element in driver.find_elements(By.CSS_SELECTOR, "textarea")
            if element.is_displayed()
        ]
        editable_count = sum(
            1
            for element in driver.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
            if element.is_displayed()
        )
    except Exception as exc:
        return f"图片上传后等待标题或正文编辑框超时，且无法读取页面状态：{exc}"

    return (
        "图片已上传，但等待标题或正文编辑框超时。"
        f"当前页面：{page_url}（{page_title}）。"
        f"可见输入框提示：{title_inputs[:8]}；"
        f"可见文本框提示：{textareas[:8]}；"
        f"可编辑区域数量：{editable_count}。"
        "请检查页面是否显示错误提示，或在打开的浏览器中手动填写标题和正文。"
    )