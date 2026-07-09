"""
디바이스 감지 및 설정 유틸리티
Mac (MPS), GPU (CUDA), CPU 자동 감지
"""
import torch
import platform
from typing import Literal

DeviceType = Literal["cuda", "mps", "cpu"]


def get_device() -> DeviceType:
    """
    사용 가능한 최적의 디바이스 자동 감지

    우선순위:
    1. CUDA (NVIDIA GPU)
    2. MPS (Apple Silicon)
    3. CPU (fallback)

    Returns:
        "cuda" | "mps" | "cpu"
    """
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        # Apple Silicon (M1/M2/M3)
        return "mps"
    else:
        return "cpu"


def get_device_info() -> dict:
    """
    현재 디바이스 정보 반환

    Returns:
        디바이스 정보 딕셔너리
    """
    device = get_device()
    info = {
        "device": device,
        "platform": platform.system(),
        "machine": platform.machine(),
        "torch_version": torch.__version__,
    }

    if device == "cuda":
        info.update({
            "cuda_version": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0),
            "gpu_count": torch.cuda.device_count(),
        })
    elif device == "mps":
        info.update({
            "mps_available": True,
            "recommendation": "Apple Silicon detected - using Metal Performance Shaders"
        })
    else:
        info.update({
            "warning": "No GPU detected - using CPU (slower performance)"
        })

    return info


def print_device_info():
    """디바이스 정보 출력"""
    info = get_device_info()
    print("=" * 50)
    print("🖥️  Device Configuration")
    print("=" * 50)
    for key, value in info.items():
        print(f"{key:20s}: {value}")
    print("=" * 50)


# 전역 디바이스 설정
DEVICE = get_device()
