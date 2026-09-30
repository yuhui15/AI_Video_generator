from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
PROFILE_DIR = Path(__file__).resolve().parent / ".browser_profile"


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
) -> uc.Chrome:
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--start-maximized")
    
    try:
        driver = uc.Chrome(options=options, version_main=153)
    except Exception:
        driver = uc.Chrome(options=options)

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


def click_publish(driver: uc.Chrome, status_callback: Callable[[str], None]) -> None:
    """全自动模式：等图片上传完成后点击“发布”，并等待发布成功的信号。"""
    status_callback("正在等待图片上传完成。")
    WebDriverWait(driver, 180).until(
        lambda d: not any(
            element.is_displayed()
            for element in d.find_elements(By.XPATH, "//*[contains(text(), '上传中')]")
        )
    )
    try:
        button = WebDriverWait(driver, 60).until(_ready_publish_button)
    except TimeoutException as exc:
        raise RuntimeError("未找到可点击的“发布”按钮。") from exc
    time.sleep(2)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    status_callback("正在点击“发布”。")
    if not _safe_click(driver, button):
        raise RuntimeError("点击“发布”按钮失败。")
    try:
        WebDriverWait(driver, 60).until(
            lambda d: "published=true" in d.current_url or bool(_visible_text_elements(d, "发布成功"))
        )
    except TimeoutException as exc:
        raise RuntimeError("已点击“发布”，但 60 秒内未看到发布成功提示，请到小红书检查。") from exc


def _ready_publish_button(driver: uc.Chrome):
    for element in driver.find_elements(By.XPATH, "//button[normalize-space(.)='发布']"):
        disabled = "disabled" in (element.get_attribute("class") or "")
        if element.is_displayed() and element.is_enabled() and not disabled:
            return element
    return False


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