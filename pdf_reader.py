import gc
import io

import fitz  # PyMuPDF
from PIL import Image


def pdf_to_images(pdf_path, max_pages=3):
    """Convert up to max_pages pages of a PDF to a list of PIL Images at 120 DPI."""
    images = []
    doc = None
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[pdf_reader] ERROR: Cannot open PDF '{pdf_path}': {e}")
        return []

    try:
        num_pages = min(len(doc), max_pages)
        # 120 DPI: PyMuPDF default is 72 DPI, so scale = 120/72
        scale = 120 / 72
        mat = fitz.Matrix(scale, scale)

        for page_num in range(num_pages):
            try:
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                # .copy() detaches the image from the buffer before we delete img_data
                img = Image.open(io.BytesIO(img_data)).copy()
                images.append(img)
                del pix
                del img_data
                gc.collect()
            except Exception as e:
                print(f"[pdf_reader] ERROR converting page {page_num + 1}: {e}")
    finally:
        doc.close()

    return images
