# OCR + Infor Document Management Uploader (Proof of Concept)

This project is a **personal proof-of-concept** application developed independently to demonstrate automation, OCR, and document processing capabilities. It is **not affiliated with or derived from any proprietary company source code or internal business data**.

## Overview

This tool automates the classification, extraction, and uploading of scanned PDF documents (like pick tickets, BOLs, invoices, etc.) into an Infor Document Management (IDM) system using API requests.

## Key Features

- Converts PDF pages into images and applies OCR using EasyOCR.
- Classifies document types based on detected text patterns.
- Extracts key fields like order numbers, PO numbers, and customer IDs.
- Automatically rotates unrecognized pages and retries OCR to improve accuracy.
- Uploads each page to the appropriate entity in IDM using encrypted credentials.
- Includes retry, logging, and error-handling mechanisms.
- Supports multiple document types including:
  - PICK TICKET
  - BILL OF LADING
  - ORDER TO BE INVOICED
  - WAREHOUSE TRANSFER PICK
  - PACK LIST
  - DELIVERY INVOICE
  - PRE-RECEIVING

## Technologies Used

- Python
- EasyOCR
- PyPDF2 & pdf2image
- Wand (for image deskewing)
- Infor IDM API integration
- OAuth2 authentication
- Encrypted credential management (using Fernet)

## Disclaimer

This project is intended solely for educational and demonstration purposes. All logic and design patterns are original and generic; no part of this code contains proprietary or confidential information from any employer or company system.

## Author

Cory Harris  
Senior Systems Engineer  
GitHub: [@corneliuscornwallis3](https://github.com/corneliuscornwallis3)

---

