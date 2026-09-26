from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"
PROFILE_DIR = Path(__file__).resolve().parent / ".browser_profile"


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
        status_callback(
            "草稿已填入浏览器。请检查图片顺序、标题和正文，并在小红书页面手动点击发布。"
        )
        return driver
    except Exception:
        driver.quit()
        raise


def _first_visible(driver, locators):
    for by, selector in locators:
        for element in driver.find_elements(by, selector):
            if element.is_displayed() and element.is_enabled():
                return element
    return False
