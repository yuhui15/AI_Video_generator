import os
import sys

def main():
    print("[INFO] Checking ModelScope dependency...")
    try:
        from modelscope import snapshot_download
    except ImportError:
        print("[INFO] Installing modelscope (using Tsinghua mirror)...")
        os.system(f"{sys.executable} -m pip install modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet")
        from modelscope import snapshot_download

    # 定义本地模型存放的目录：./models/clip-vit-large-patch14
    model_dir = os.path.join(os.path.dirname(__file__), "models", "clip-vit-large-patch14")
    os.makedirs(model_dir, exist_ok=True)
    print(f"[INFO] Local model directory: {model_dir}")

    # 检查是否已经下载过（通过判断关键配置文件是否存在）
    if os.path.exists(os.path.join(model_dir, "config.json")):
        print("[INFO] 🎉 CLIP model already exists locally. Skipping download.")
        return

    print("[INFO] Downloading CLIP model via ModelScope domestic mirror (this may take a few minutes for 1.7GB)...")
    try:
        snapshot_download('AI-ModelScope/clip-vit-large-patch14', local_dir=model_dir)
        print("[INFO] 🎉 CLIP model downloaded successfully!")
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()