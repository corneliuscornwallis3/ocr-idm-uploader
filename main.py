from ocr_uploader.processor import process_pdf
import argparse

def main():
    parser = argparse.ArgumentParser(description="OCR PDF document processor")
    parser.add_argument("pdf_path", help="Path to input PDF file")
    args = parser.parse_args()

    process_pdf(args.pdf_path)

if __name__ == "__main__":
    main()
