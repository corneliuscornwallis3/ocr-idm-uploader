from ocr_uploader.utils import load_pdf_pages, rotate_image
from ocr_uploader.classifier import classify_text
from ocr_uploader.uploader import mock_upload
from easyocr import Reader

reader = Reader(['en'], gpu=False)

def process_pdf(pdf_path):
    pages = load_pdf_pages(pdf_path)
    for i, image in enumerate(pages):
        for angle in [0, 90, 180, 270]:
            rotated = rotate_image(image, angle)
            result = reader.readtext(rotated, detail=0)
            full_text = " ".join(result)
            if full_text.strip():
                doc_type = classify_text(full_text)
                print(f"Page {i+1}: Classified as {doc_type}")
                mock_upload(pdf_path, doc_type, full_text)
                break
