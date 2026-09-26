import os
import re
import time
import requests
from urllib.parse import quote, unquote
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# 尝试导入图像处理库
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# 尝试导入本地高精度多模态模型 CLIP (openai/clip-vit-large-patch14)
try:
    import torch
    from PIL import Image
    from transformers import CLIPProcessor, CLIPModel
    
    print("🔄 正在本地加载高精度 CLIP 模型 (openai/clip-vit-large-patch14)...")
    CLIP_MODEL_NAME = "openai/clip-vit-large-patch14"
    clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
    clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)
    clip_model.eval()
    CLIP_AVAILABLE = True
    print("✅ 高精度 CLIP 模型加载成功！将对真人脸部、单人、眼睛可见性进行严苛质检。")
except ImportError:
    CLIP_AVAILABLE = False
    print("⚠️ 未检测到 transformers/torch，请通过 pip install transformers torch 安装。")

def is_valid_face_image(image_path):
    """
    基础图像校验：使用 np.fromfile + cv2.imdecode 彻底解决 Windows 下中文路径读取失败的问题，
    并过滤掉过小的缩略图。
    """
    if not CV2_AVAILABLE:
        return True
    try:
        stream = np.fromfile(image_path, dtype=np.uint8)
        image = cv2.imdecode(stream, cv2.IMREAD_COLOR)
        if image is None:
            return False
        h, w, _ = image.shape
        if h < 250 or w < 250:
            return False
        return True
    except Exception:
        return False

def check_image_matches_metric(image_path, prob_threshold=0.5):
    """
    高精度 CLIP 统一质检：
    - 正向：单张清晰的真人脸部照片，真人肖像，眼睛未被遮挡。
    - 负向：卡通、动漫、插画、美学概念图、技术图表、多人合照、眼睛被遮挡（墨镜/口罩）。
    """
    if not CLIP_AVAILABLE:
        return True
    
    try:
        image = Image.open(image_path).convert("RGB")
        
        # 统一正向提示词
        pos_text = "A clear, high-quality photograph of a single real human face, real person portrait, with visible eyes, no text."
        # 统一负向提示词
        neg_text = neg_text = "A cartoon, anime, illustration, drawing, aesthetic concept diagram, technical drawing, multiple people, group photo, eyes covered, sunglasses, mask, blurry, collage, low resolution, heavy text, text overlay, watermarks, typography, words."
        
        texts = [pos_text, neg_text]
        inputs = clip_processor(text=texts, images=image, return_tensors="pt", padding=True)
        
        with torch.no_grad():
            outputs = clip_model(**inputs)
            logits_per_image = outputs.logits_per_image / 100.0
            probs = logits_per_image.softmax(dim=-1)
            
        pos_prob = probs[0][0].item() # 符合真人的概率
        neg_prob = probs[0][1].item() # 命中违规（卡通/图表/多人/遮挡）的概率
        
        if pos_prob >= prob_threshold and neg_prob < (1.0 - prob_threshold):
            return True
        else:
            return False
            
    except Exception as e:
        print(f"   [警告] CLIP 校验出错: {e}")
        return True

def crawl_all_63_metrics_bing_clip(metrics_dict, target_count_per_category=20, base_save_dir=r"C:\Users\sunyu\Desktop\全套63项美学指标数据集_高精质检20张"):
    """
    使用 Bing 元素解析搜索 + 高精度 CLIP 质检全自动抓取 63 个美学指标。
    """
    if not os.path.exists(base_save_dir):
        os.makedirs(base_save_dir)

    options = uc.ChromeOptions()
    try:
        driver = uc.Chrome(options=options, version_main=153)
    except Exception as e:
        print(f"指定版本启动失败，尝试默认启动... 错误: {e}")
        driver = uc.Chrome(options=options)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for chinese_metric_name, levels in metrics_dict.items():
        print(f"\n==================== 正在处理美学指标: [{chinese_metric_name}] ====================")
        
        metric_dir = os.path.join(base_save_dir, chinese_metric_name)
        
        for level, info in levels.items():
            keyword = info["query"]
            level_desc = info["desc"]
            
            level_dir = os.path.join(metric_dir, level)
            if not os.path.exists(level_dir):
                os.makedirs(level_dir)
                
            existing_files = [f for f in os.listdir(level_dir) if f.endswith(('.jpg', '.png', '.jpeg', '.webp'))]
            success_count = len(existing_files)
            
            if success_count >= target_count_per_category:
                print(f"   [已完成] 目标级别 [{level.upper()} -> {level_desc}] 已存有 {success_count} 张合格照片，跳过。")
                continue

            page_scroll_attempts = 0
            max_scrolls = 6
            
            while success_count < target_count_per_category and page_scroll_attempts < max_scrolls:
                print(f"\n🚀 目标级别 [{level.upper()} -> {level_desc}] -> 当前进度: {success_count}/{target_count_per_category} 张，正在通过 Bing 搜索...")
                
                encoded_keyword = quote(keyword)
                search_url = f"https://www.bing.com/images/search?q={encoded_keyword}"
                driver.get(search_url)
                time.sleep(3)

                for _ in range(page_scroll_attempts + 1):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                img_urls = set()
                try:
                    # 通过 Selenium 精准获取 Bing 图片卡片原图链接
                    thumb_elements = driver.find_elements(By.CSS_SELECTOR, "a.iusc")
                    for elem in thumb_elements:
                        m_attr = elem.get_attribute("m")
                        if m_attr:
                            match = re.search(r'"murl":"(https?://[^"]+)"', m_attr)
                            if match:
                                url = unquote(match.group(1))
                                if "bing.com" not in url:
                                    if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                                        img_urls.add(url)
                except Exception as e:
                    print(f"   [警告] 解析页面元素时出错: {e}")

                final_urls = list(img_urls)
                print(f"   Bing 成功解析到候选链接 {len(final_urls)} 个，开始高精度 CLIP 模型逐一质检...")

                old_success_count = success_count

                for url in final_urls:
                    if success_count >= target_count_per_category:
                        break
                    try:
                        res = requests.get(url, headers=headers, timeout=8)
                        if res.status_code == 200 and len(res.content) > 18000:
                            ext = "jpg"
                            url_lower = url.lower()
                            if ".png" in url_lower: ext = "png"
                            elif ".webp" in url_lower: ext = "webp"
                            elif ".jpeg" in url_lower: ext = "jpeg"

                            temp_filename = os.path.join(level_dir, f"temp_{time.time()}_{success_count}.{ext}")
                            with open(temp_filename, 'wb') as f:
                                f.write(res.content)

                            # 1. 基础尺寸与读取校验
                            if is_valid_face_image(temp_filename):
                                # 2. 高精度 CLIP 校验（真人、单人、眼睛未被遮挡）
                                if check_image_matches_metric(temp_filename):
                                    success_count += 1
                                    final_filename = os.path.join(level_dir, f"{chinese_metric_name}_{level_desc}_{success_count:02d}.{ext}")
                                    os.rename(temp_filename, final_filename)
                                    print(f"   [{success_count}/{target_count_per_category}] ✅ 质检通过并保存: {os.path.basename(final_filename)}")
                                else:
                                    os.remove(temp_filename)
                            else:
                                os.remove(temp_filename)
                    except Exception:
                        pass
                
                if success_count == old_success_count:
                    print(f"   [提示] 本轮未获得新增合格图片，继续加载...")

                page_scroll_attempts += 1

            if success_count < target_count_per_category:
                print(f"   ⚠️ [跳过] 目标级别 [{level.upper()} -> {level_desc}] 有效图片不足 20 张（最终收集到 {success_count} 张），自动跳至下一指标。")

    driver.quit()
    print(f"\n🎉 全部 63 个美学指标数据集采集流程圆满结束！\n📁 有效数据集保存在: {base_save_dir}")

if __name__ == "__main__":
    comprehensive_63_metrics = {
        "眉宽面宽比": {"high": {"query": "site:looksmax.org high brow length to face width ratio person", "desc": "高"}, "low": {"query": "site:looksmax.org low brow length to face width ratio", "desc": "低"}},
        "颈宽": {"high": {"query": "site:looksmax.org wide neck width model portrait", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow neck width person", "desc": "窄"}},
        "面部长宽比": {"high": {"query": "site:looksmax.org high fwhr face width to height ratio", "desc": "高"}, "low": {"query": "site:looksmax.org low fwhr narrow face person", "desc": "低"}},
        "唇厚比": {"high": {"query": "site:looksmax.org lower lip to upper lip ratio full lips", "desc": "下唇厚"}, "low": {"query": "site:looksmax.org thin lower lip upper lip ratio", "desc": "下唇薄"}},
        "眉毛低矮度": {"high": {"query": "site:looksmax.org low set eyebrows compact face", "desc": "低矮"}, "low": {"query": "site:looksmax.org high set eyebrows spaced", "desc": "高挑"}},
        "颧骨高度": {"high": {"query": "site:looksmax.org high cheekbone height prominent cheeks", "desc": "高"}, "low": {"query": "site:looksmax.org low cheekbone flat midface", "desc": "低"}},
        "眼距比例": {"high": {"query": "site:looksmax.org wide set eyes separation ratio face", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow eye separation ratio closely set", "desc": "窄"}},
        "耳外张角度": {"high": {"query": "site:looksmax.org protruding ears ear protrusion angle", "desc": "大角度"}, "low": {"query": "site:looksmax.org pinned back flat ears angle", "desc": "小角度"}},
        "下颌倾斜角": {"high": {"query": "site:looksmax.org steep jaw slope facial angle", "desc": "大倾斜"}, "low": {"query": "site:looksmax.org flat jaw slope line", "desc": "平缓"}},
        "外眼角倾斜角": {"high": {"query": "site:looksmax.org positive lateral canthal tilt eyes", "desc": "正倾斜"}, "low": {"query": "site:looksmax.org negative lateral canthal tilt drooping", "desc": "负倾斜"}},
        "鼻梁鼻宽比": {"high": {"query": "site:looksmax.org high nose bridge to nose width ratio", "desc": "高比值"}, "low": {"query": "site:looksmax.org low nose bridge width ratio", "desc": "低比值"}},
        "唇峰深度": {"high": {"query": "site:looksmax.org deep cupid bow depth lips sharp", "desc": "深"}, "low": {"query": "site:looksmax.org flat cupid bow lip border", "desc": "浅平"}},
        "瞳距口宽比": {"high": {"query": "site:looksmax.org interpupillary mouth width ratio face", "desc": "大比值"}, "low": {"query": "site:looksmax.org narrow interpupillary mouth ratio", "desc": "小比值"}},
        "颞部宽度": {"high": {"query": "site:looksmax.org wide bitemporal width upper face", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow bitemporal width temples", "desc": "窄"}},
        "眼裂长宽比": {"high": {"query": "site:looksmax.org high eye aspect ratio wide open eyes", "desc": "高"}, "low": {"query": "site:looksmax.org low eye aspect ratio narrow slit eyes", "desc": "低"}},
        "口宽鼻宽比": {"high": {"query": "site:looksmax.org mouth width to nose width ratio aesthetic", "desc": "大"}, "low": {"query": "site:looksmax.org small mouth to nose width ratio", "desc": "小"}},
        "中庭比例": {"high": {"query": "site:looksmax.org long midface ratio stretched face", "desc": "长"}, "low": {"query": "site:looksmax.org short compact midface ratio", "desc": "短"}},
        "中庭占比": {"high": {"query": "site:looksmax.org long middle third face proportion", "desc": "高占比"}, "low": {"query": "site:looksmax.org short middle third face", "desc": "低占比"}},
        "上庭占比": {"high": {"query": "site:looksmax.org long top third forehead proportion", "desc": "高占比"}, "low": {"query": "site:looksmax.org short top third forehead", "desc": "低占比"}},
        "下庭占比": {"high": {"query": "site:looksmax.org long lower third chin jaw proportion", "desc": "高占比"}, "low": {"query": "site:looksmax.org short lower third face", "desc": "低占比"}},
        "总面部宽高比": {"high": {"query": "site:looksmax.org total facial width to height ratio wide", "desc": "高"}, "low": {"query": "site:looksmax.org low total facial width height ratio", "desc": "低"}},
        "单眼间距测试": {"high": {"query": "site:looksmax.org one eye apart test wide eyes distance", "desc": "宽"}, "low": {"query": "site:looksmax.org close one eye apart test distance", "desc": "窄"}},
        "眉倾斜角": {"high": {"query": "site:looksmax.org tilted eyebrows angle face person", "desc": "大倾斜"}, "low": {"query": "site:looksmax.org horizontal flat eyebrows angle", "desc": "水平"}},
        "鼻尖位置": {"high": {"query": "site:looksmax.org projected nose tip position high", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed nose tip position", "desc": "后缩"}},
        "内眼角鼻宽比": {"high": {"query": "site:looksmax.org intercanthal nasal width ratio wide", "desc": "大"}, "low": {"query": "site:looksmax.org narrow intercanthal nasal width ratio", "desc": "小"}},
        "同侧鼻翼角": {"high": {"query": "site:looksmax.org ipsilateral alar angle nose width", "desc": "大"}, "low": {"query": "site:looksmax.org narrow ipsilateral alar angle", "desc": "小"}},
        "鼻翼角与下颌前额角偏差": {"high": {"query": "site:looksmax.org deviation of ipsilateral alar angle jaw angle", "desc": "大偏差"}, "low": {"query": "site:looksmax.org low deviation alar jaw angle", "desc": "小偏差"}},
        "嘴角位置": {"high": {"query": "site:looksmax.org wide mouth corner position smile", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow mouth corner position", "desc": "窄"}},
        "下巴人中比": {"high": {"query": "site:looksmax.org chin to philtrum ratio long chin", "desc": "大比值"}, "low": {"query": "site:looksmax.org short chin to philtrum ratio", "desc": "小比值"}},
        "下颌额面角": {"high": {"query": "site:looksmax.org wide jaw frontal angle square face", "desc": "大"}, "low": {"query": "site:looksmax.org narrow jaw frontal angle v-line", "desc": "小"}},
        "下颌角宽度": {"high": {"query": "site:looksmax.org wide bigonial width jawline square", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow bigonial width tapered face", "desc": "窄"}},
        "下庭比例": {"high": {"query": "site:looksmax.org lower third proportion long chin", "desc": "大"}, "low": {"query": "site:looksmax.org short lower third proportion", "desc": "小"}},
        "耳外张比例": {"high": {"query": "site:looksmax.org ear protrusion ratio protruding ears", "desc": "高比例"}, "low": {"query": "site:looksmax.org low ear protrusion ratio flat ears", "desc": "低比例"}},
        "鼻尖角": {"high": {"query": "site:looksmax.org obtuse nasal tip angle definition", "desc": "钝角"}, "low": {"query": "site:looksmax.org acute nasal tip angle sharp", "desc": "锐角"}},
        "面部突度鼻根点": {"high": {"query": "site:looksmax.org facial convexity nasion angle high", "desc": "凸度大"}, "low": {"query": "site:looksmax.org straight facial convexity nasion", "desc": "平直"}},
        "内部中庭前突角": {"high": {"query": "site:looksmax.org interior midface projection angle", "desc": "大"}, "low": {"query": "site:looksmax.org flat interior midface angle", "desc": "平"}},
        "下颌颈夹角": {"high": {"query": "site:looksmax.org obtuse submental cervical angle double chin", "desc": "钝角"}, "low": {"query": "site:looksmax.org sharp submental cervical angle tight neck", "desc": "锐角紧致"}},
        "鼻前突度": {"high": {"query": "site:looksmax.org high nasal projection sharp nose", "desc": "高"}, "low": {"query": "site:looksmax.org underprojected flat nose", "desc": "低"}},
        "鼻面角": {"high": {"query": "site:looksmax.org high nasofacial angle prominent nose", "desc": "大"}, "low": {"query": "site:looksmax.org low nasofacial angle flat nose", "desc": "小"}},
        "眶矢量": {"high": {"query": "site:looksmax.org positive orbital vector deep set eyes", "desc": "正矢量"}, "low": {"query": "site:looksmax.org negative orbital vector scleral show", "desc": "负矢量"}},
        "鼻尖旋转角": {"high": {"query": "site:looksmax.org upturned nose tip rotation angle high", "desc": "高旋"}, "low": {"query": "site:looksmax.org downturned nose tip rotation angle", "desc": "下垂"}},
        "鼻额角": {"high": {"query": "site:looksmax.org obtuse nasofrontal angle flat forehead", "desc": "钝角大"}, "low": {"query": "site:looksmax.org acute nasofrontal angle deep brow", "desc": "锐角深邃"}},
        "下唇伯斯通线": {"high": {"query": "site:looksmax.org lower lip burstone line protruding", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed lower lip burstone line", "desc": "后缩"}},
        "相对于法兰克福平面的后缩度": {"high": {"query": "site:looksmax.org recession relative to frankfort plane high", "desc": "大后缩"}, "low": {"query": "site:looksmax.org forward relative to frankfort plane", "desc": "前突"}},
        "鼻宽长比": {"high": {"query": "site:looksmax.org high nasal width to height ratio", "desc": "宽"}, "low": {"query": "site:looksmax.org narrow nasal width to height ratio", "desc": "窄"}},
        "下颌角角度": {"high": {"query": "site:looksmax.org obtuse gonial angle soft jawline", "desc": "钝角"}, "low": {"query": "site:looksmax.org acute gonial angle jawline sharp", "desc": "锐角"}},
        "前面部深度": {"high": {"query": "site:looksmax.org high anterior facial depth projection", "desc": "深"}, "low": {"query": "site:looksmax.org shallow anterior facial depth", "desc": "浅"}},
        "霍尔代威H线": {"high": {"query": "site:looksmax.org holdaway h line protruding lips profile", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed holdaway h line profile", "desc": "后缩"}},
        "上唇S线位置": {"high": {"query": "site:looksmax.org upper lip s-line position forward", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed upper lip s-line position", "desc": "后缩"}},
        "颏唇角": {"high": {"query": "site:looksmax.org obtuse mentolabial angle chin fold", "desc": "钝角"}, "low": {"query": "site:looksmax.org acute mentolabial angle sharp fold", "desc": "锐角"}},
        "上额倾斜度": {"high": {"query": "site:looksmax.org sloped upper forehead angle high", "desc": "倾斜大"}, "low": {"query": "site:looksmax.org vertical upright upper forehead", "desc": "垂直"}},
        "眉弓倾斜角": {"high": {"query": "site:looksmax.org browridge inclination angle prominent brow", "desc": "大"}, "low": {"query": "site:looksmax.org flat browridge inclination angle", "desc": "平"}},
        "面部突度眉间点": {"high": {"query": "site:looksmax.org facial convexity glabella angle high", "desc": "大"}, "low": {"query": "site:looksmax.org flat facial convexity glabella", "desc": "平"}},
        "总面部突度": {"high": {"query": "site:looksmax.org total facial convexity angle high", "desc": "大"}, "low": {"query": "site:looksmax.org flat total facial convexity", "desc": "平"}},
        "面部深高比": {"high": {"query": "site:looksmax.org facial depth to height ratio high", "desc": "高"}, "low": {"query": "site:looksmax.org low facial depth to height ratio", "desc": "低"}},
        "Z角": {"high": {"query": "site:looksmax.org high z angle profile aesthetic jaw", "desc": "大"}, "low": {"query": "site:looksmax.org low z angle recessed profile", "desc": "小"}},
        "鼻唇角": {"high": {"query": "site:looksmax.org obtuse nasolabial angle nose profile", "desc": "大"}, "low": {"query": "site:looksmax.org acute nasolabial angle nose", "desc": "小"}},
        "法兰克福尖角": {"high": {"query": "site:looksmax.org high frankfort tip angle profile", "desc": "大"}, "low": {"query": "site:looksmax.org low frankfort tip angle", "desc": "小"}},
        "下唇E线位置": {"high": {"query": "site:looksmax.org lower lip e-line position protruding", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed lower lip e-line position", "desc": "后缩"}},
        "上唇E线位置": {"high": {"query": "site:looksmax.org upper lip e-line position protruding", "desc": "前突"}, "low": {"query": "site:looksmax.org recessed upper lip e-line position", "desc": "后缩"}},
        "下颌平面角": {"high": {"query": "site:looksmax.org steep mandibular plane angle long face", "desc": "高角"}, "low": {"query": "site:looksmax.org flat mandibular plane angle horizontal", "desc": "平角"}},
        "下颌支与下颌比": {"high": {"query": "site:looksmax.org high ramus to mandible ratio long ramus", "desc": "高"}, "low": {"query": "site:looksmax.org low ramus to mandible ratio short ramus", "desc": "低"}},
        "下颌角至口裂线距离": {"high": {"query": "site:looksmax.org long gonion to mouth line distance", "desc": "长"}, "low": {"query": "site:looksmax.org short gonion to mouth line distance", "desc": "短"}}
    }

    crawl_all_63_metrics_bing_clip(comprehensive_63_metrics, target_count_per_category=20)