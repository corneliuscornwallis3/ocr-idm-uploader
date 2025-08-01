from pdf2image import convert_from_path
from PIL import Image

def load_pdf_pages(pdf_path):
    return convert_from_path(pdf_path)

def rotate_image(image, angle):
    return image.rotate(angle, expand=True)
