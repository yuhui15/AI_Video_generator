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


def open_filled_draft(
    image_paths: list[Path],
    title: str,
    content: str,
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
        file_input = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]'))
        )
        file_input.send_keys("\n".join(str(path.resolve()) for path in image_paths))
        status_callback("图片已上传，正在等待编辑器加载。")

        try:
            title_input = wait.until(
                lambda browser: _first_visible(
                    browser,
                    (
                        (By.CSS_SELECTOR, 'input[placeholder*="标题"]'),
                        (By.CSS_SELECTOR, 'input[placeholder*="填写标题"]'),
                        (By.CSS_SELECTOR, 'input[class*="title"]'),
                    ),
                )
            )
            title_input.clear()
            title_input.send_keys(title)

            editor = wait.until(
                lambda browser: _first_visible(
                    browser,
                    (
                        (By.CSS_SELECTOR, '[contenteditable="true"]'),
                        (By.CSS_SELECTOR, "textarea[placeholder*='正文']"),
                        (By.CSS_SELECTOR, "textarea[placeholder*='描述']"),
                    ),
                )
            )
            editor.click()
            editor.send_keys(content)
        except TimeoutException as exc:
            raise PublisherEditorNotFound(
                driver,
                _describe_missing_editor(driver),
            ) from exc
        status_callback(
            "草稿已填入浏览器。请检查图片顺序、标题和正文，并在小红书页面手动点击发布。"
        )
        return driver
    except PublisherEditorNotFound:
        raise
    except Exception:
        driver.quit()
        raise


def _first_visible(driver, locators):
    for by, selector in locators:
        for element in driver.find_elements(by, selector):
            if element.is_displayed() and element.is_enabled():
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
        "请检查浏览器是否要求登录、是否显示错误提示，或在打开的浏览器中手动填写标题和正文。"
        "浏览器会保持打开，不会自动发布。"
    )
