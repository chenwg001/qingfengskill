#!/usr/bin/env python3
"""
依赖检测脚本 - 检查 qingfeng-VE 技能所需的外部依赖
"""
import sys
import subprocess
import os

def check_command(cmd):
    """检查命令是否可用"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def check_python_package(package):
    """检查 Python 包是否安装"""
    try:
        __import__(package.replace('-', '_'))
        return True
    except ImportError:
        return False

def get_version(cmd):
    """获取命令版本"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            return lines[0] if lines else "unknown"
    except:
        pass
    return "not found"

def main():
    print("=" * 60)
    print("qingfeng-VE 技能依赖检测")
    print("=" * 60)
    print()

    results = []

    # 1. FFmpeg
    print("1. FFmpeg (必需)")
    ffmpeg_found = check_command("ffmpeg -version")
    if ffmpeg_found:
        version = get_version("ffmpeg -version")
        print(f"   ✓ 已安装: {version.split()[0] if version else 'unknown'}")
        results.append(("FFmpeg", True, version))
    else:
        print("   ✗ 未安装")
        print("   → 安装方式:")
        print("     Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH")
        print("     macOS:   brew install ffmpeg")
        print("     Linux:   sudo apt install ffmpeg")
        results.append(("FFmpeg", False, None))
    print()

    # 2. edge-tts
    print("2. edge-tts (必需，用于在线配音)")
    edge_tts_installed = check_python_package("edge_tts")
    if edge_tts_installed:
        import edge_tts
        print(f"   ✓ 已安装: {edge_tts.__version__}")
        results.append(("edge-tts", True, edge_tts.__version__))
    else:
        print("   ✗ 未安装")
        print("   → 安装命令: pip install edge-tts")
        results.append(("edge-tts", False, None))
    print()

    # 3. Pillow
    print("3. Pillow (必需，用于图片处理)")
    pillow_installed = check_python_package("PIL")
    if pillow_installed:
        from PIL import Image
        print(f"   ✓ 已安装: {Image.__version__}")
        results.append(("Pillow", True, Image.__version__))
    else:
        print("   ✗ 未安装")
        print("   → 安装命令: pip install Pillow")
        results.append(("Pillow", False, None))
    print()

    # 4. numpy
    print("4. numpy (必需，用于音频处理)")
    numpy_installed = check_python_package("numpy")
    if numpy_installed:
        import numpy
        print(f"   ✓ 已安装: {numpy.__version__}")
        results.append(("numpy", True, numpy.__version__))
    else:
        print("   ✗ 未安装")
        print("   → 安装命令: pip install numpy")
        results.append(("numpy", False, None))
    print()

    # 5. 本地 TTS（可选）
    print("5. Qwen3-TTS 本地克隆（可选）")
    model_dir = os.environ.get("QWEN_TTS_MODEL_DIR")
    python_exe = os.environ.get("QWEN_TTS_PYTHON")
    if model_dir and python_exe and os.path.exists(model_dir) and os.path.exists(python_exe):
        print(f"   ✓ 已配置")
        print(f"      模型目录: {model_dir}")
        print(f"      Python路径: {python_exe}")
        results.append(("Qwen3-TTS", True, "configured"))
    else:
        print("   ○ 未配置（不影响基本功能）")
        print("   → 如需使用本地克隆，请设置环境变量:")
        print("     QWEN_TTS_MODEL_DIR=/path/to/model")
        print("     QWEN_TTS_PYTHON=/path/to/python")
        results.append(("Qwen3-TTS", False, "not configured"))
    print()

    # 总结
    print("=" * 60)
    print("检测结果汇总")
    print("=" * 60)
    
    all_ok = all(r[1] for r in results if r[0] != "Qwen3-TTS")  # 本地TTS是可选的
    
    if all_ok:
        print("✓ 所有必需依赖已安装，技能可以正常使用")
    else:
        missing = [r[0] for r in results if not r[1]]
        print(f"✗ 缺少以下必需依赖: {', '.join(missing)}")
        print("  请安装后重新运行检测")
    
    print()
    print("提示: 本地 TTS 克隆为可选功能，不安装也不影响基本剪辑")
    print("=" * 60)
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
