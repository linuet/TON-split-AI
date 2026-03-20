from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


def preprocess_receipt_image(source_path: Path, output_path: Path) -> Path:
    image = Image.open(source_path).convert("RGB")
    image = ImageOps.exif_transpose(image)
    image = ImageEnhance.Contrast(image).enhance(1.6)
    image = ImageEnhance.Sharpness(image).enhance(1.8)

    arr = np.array(image)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    adaptive = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12
    )
    denoised = cv2.fastNlMeansDenoising(adaptive, None, 10, 7, 21)
    rgb = cv2.cvtColor(denoised, cv2.COLOR_GRAY2RGB)
    result = Image.fromarray(rgb)
    result.save(output_path, format="JPEG", quality=95)
    return output_path
