import time
import logging
import os
from PIL import Image as PILImage
from pdf2image import convert_from_path
import easyocr
import re
import PyPDF2
import shutil
from wand.image import Image
import base64
import json
import requests
from requests_oauthlib import OAuth2Session
from requests.auth import HTTPBasicAuth
import config
from cryptography.fernet import Fernet
from wand.color import Color

# Setting up logging
logging.basicConfig(filename="app.log", level=logging.DEBUG, format='%(asctime)s | %(levelname)s:%(name)s:%(message)s')
logging.getLogger("PIL").setLevel(logging.ERROR)

# Initialize folder paths
sfolder_path = config.sfolder_path
temp_directory = config.temp_directory
deliver_directory = config.deliver_directory
error_directory = config.error_directory
archive_directory = config.archive_directory
other_directory = config.other_directory

def decrypt_secret():
    with open("secret.key", "rb") as key_file:
        key = key_file.read()
    f = Fernet(key)

    with open("credentials.enc", "rb") as encrypted_file:
        encrypted_credentials = encrypted_file.read()

    decrypted_credentials = json.loads(f.decrypt(encrypted_credentials).decode())

    return decrypted_credentials

# Decrypt secret and credentials
decrypted_creds = decrypt_secret()

# OAuth 2.0 client credentials 
client_id = config.client_id
client_secret = decrypted_creds["client_secret"]
saak = decrypted_creds["saak"]
sask = decrypted_creds["sask"]
token_url = config.token_url
api_url = config.api_url

# Initialize form title variables
OE_PICK = "PICK TICKET"
WT_PICK = "WAREHOUSE TRANSFER PICK"
BOL = "BILL OF LADING"
OTBI = "ORDER TO BE INVOICED"
PRE_RECEIVING = "PRE-RECEIVING"
PACK_LIST = "PACK LIST"
DELIVERY_INVOICE = "DELIVERY INVOICE"

UNKNOWN = "UNKNOWN"


def main():
    logging.info("<-------------------------Python app started---------------------------------->")

    try:
        # This will keep the program alive
        while True:
            # Create file reference array
            myFiles = get_files_from_folder(sfolder_path)
            if len(myFiles) == 0: logging.info(f"No files found at {sfolder_path}")
            # Loop through files
            for item in myFiles:
                
                # clear processing directories
                clear_directory(temp_directory)
                clear_directory(deliver_directory)
                
                # extracted_text is a list pages represented by a concatenated string for all page data
                
                page_num = 0
                orig_filename_no_ext = os.path.splitext(os.path.basename(item))[0] # filename without type extension
                extracted_text = extract_text_from_pdf(item)
                # loop through pages
                page_index = 0
                while page_index < len(extracted_text):
                    page = extracted_text[page_index]
                    page_num = page_index + 1
                    img_path = f"Pick Tickets/temp/output_page_{page_num}.jpg"

                    form_type = get_form_type(page[0])

                    if form_type is None:
                        logging.info(f"File: {orig_filename_no_ext} Page: {page_num} not recognized. Attempting rotation and retry...")
                        rotations = [90, 180]

                        for angle in rotations:
                            img = PILImage.open(img_path).rotate(angle, expand=True)
                            img.save(img_path)
                            reader = easyocr.Reader(['en'], gpu=False, verbose=False)
                            rotated_result = reader.readtext(img_path, detail=0, paragraph=True)
                            rotated_text = ' '.join(rotated_result)
                            print(f"<< File: {orig_filename_no_ext} Page: {page_num} data rotated {angle} degrees >> {rotated_text}\n")
                            rotated_form_type = get_form_type(rotated_text)

                            if rotated_form_type:
                                logging.info(f"Rotation {angle}° fixed Page {page_num}. Reprocessing...")
                                extracted_text[page_index][0] = rotated_text
                                form_type = rotated_form_type
                                break

                        if form_type is None:
                            logging.info(f"File: {orig_filename_no_ext} Page: {page_num} still unrecognized after all rotations.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{other_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            page_index += 1
                            continue

                    text_content = extracted_text[page_index][0]

                    if form_type == OE_PICK:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        custno = extract_cust_number(text_content)
                        orderno = extract_orderNo(text_content)
                        pono = extract_poNo(text_content)
                        sro_num = extract_serviceNo(text_content)
                        if pono == '': pono = None
                        if custno and orderno:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_OE(pono, custno, orderno, sro_num, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Cust #: {custno}, Order #: {orderno}, Customer PO #: {pono}, SRO#: {sro_num}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. Missing data.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == WT_PICK:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        transferno = extract_transferNo(text_content)
                        if transferno:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_WT(transferno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Transfer #: {transferno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. Transfer number missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == OTBI:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        serviceNo = extract_serviceNo(text_content)
                        custno = extract_cust_numberOTBI(text_content)
                        if serviceNo:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_OTBI(serviceNo, custno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Service #: {serviceNo} Cust #: {custno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. Service number missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == BOL:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        transferno = extract_BOLtransferNo(text_content)
                        orderno = extract_BOLorderNo(text_content)
                        b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                        if transferno:
                            request_pl = create_payload_BOL(transferno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Transfer #: {transferno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        elif orderno:
                            request_pl = create_payload_BOL(orderno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Order #: {orderno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. BOL data missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == PRE_RECEIVING:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        transferno = extract_transferNo(text_content)
                        if transferno:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_PR(transferno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! PO #: {transferno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. Transfer number missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == PACK_LIST:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        transferno = extract_transferNo(text_content)
                        if transferno:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_PL(transferno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! PO #: {transferno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. PO number missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    elif form_type == DELIVERY_INVOICE:
                        print(f"<< File: {orig_filename_no_ext} Page: {page_num} data >> {text_content}\n")
                        orderno = extract_orderNoDSD(text_content)
                        if orderno:
                            b64 = file_to_base64(f"{deliver_directory}/page_{page_num}.pdf")
                            request_pl = create_payload_DSD(orderno, b64)
                            response_code = send_request(request_pl)
                            if response_code == 200:
                                logging.info(f"File: {orig_filename_no_ext} Page: {page_num} processed successfully! Order #: {orderno}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{archive_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                            else:
                                logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. response code: {response_code}")
                                shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")
                        else:
                            logging.error(f"File: {orig_filename_no_ext} Page: {page_num} not processed. Order # missing.")
                            shutil.move(f"{deliver_directory}/page_{page_num}.pdf", f"{error_directory}/{orig_filename_no_ext}_page_{page_num}.pdf")

                    page_index += 1

                logging.info("<<EOF>>")
                # clear processing directories
                clear_directory(temp_directory)
                clear_directory(deliver_directory)
                try:
                    os.remove(item)
                except Exception as e:
                    logging.error(f"An error occurred: {e}")
            logging.info("<---------------------------Done Processing--------------------------------->")

            logging.info("---App is still running...---")
            time.sleep(60)  # Sleeps for 1 minute before checking again
    except KeyboardInterrupt:
        logging.info("Python app stopped.")
        pass

def get_files_from_folder(folder_path):
    # Get a list of files in the specified folder
    files = []
    
    # Check if the folder exists
    if os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            # Only add files (ignore directories)
            if os.path.isfile(file_path):
                files.append(file_path)
    
    return files

# Function to pre-process and extract text from images in a PDF
def extract_text_from_pdf(pdf_path):
        
    text = []
    reader = easyocr.Reader(['en'],gpu=False,verbose=False)
    img = convert_from_path(pdf_path)
    split_pdf(pdf_path,deliver_directory) # Save each page as an individual file for sending to IDM

    # Save each page as a .jpg
    for i, image in enumerate(img):
        image.save(f"Pick Tickets/temp/output_page_{i+1}.jpg","JPEG")
    # run OCR on each page image and return a list of pages, each page a single string delimited by a space between elements
    for j in range(len(img)):
        img_path = f"Pick Tickets/temp/output_page_{j+1}.jpg"
        # Deskew the image
        with Image(filename=img_path) as img:
            img.deskew(0.4*img.quantum_range)
            img.save(filename=img_path)
        
        result = reader.readtext(img_path,detail=0,paragraph=True)
        temp_str = ''
        for k in result:
            temp_str += k+" "
        text.append([temp_str])
            
    return text

def get_form_type(text):
    # Check for the presence of "WAREHOUSE TRANSFER PICK"
    if "WAREHOUSE TRANSFER PICK" in text.upper():
        return "WAREHOUSE TRANSFER PICK"
    
    # Check for the presence of "PICK TICKET"
    elif "PICK TICKET" in text.upper():
        return "PICK TICKET"
    
    elif "BILL OF LADING" in text.upper():
        return "BILL OF LADING"
    
    elif "ORDER TO BE INVOICED" in text.upper():
        return "ORDER TO BE INVOICED"
    
    elif "PRE-RECEIVING" in text.upper():
        return "PRE-RECEIVING"
    
    elif any(term in text.upper() for term in ("PACKING LIST", "PACKING SLIP", "DELIVERY SLIP")):
        return "PACK LIST"
    
    elif "DELIVERY INVOICE" in text.upper():
        return "DELIVERY INVOICE"
    
    # Return None if neither is found
    else:
        return None

def extract_cust_number(text):
    # Regular expression to find digits between "CUST #:" and the next space
    pattern = r"CUST\s*(\D*)?\s+(\d+)\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(2).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found
    
def extract_cust_numberOTBI(text):

    pattern = r"(?<=Bill To)\s+(\d+)\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found

def extract_poNo(text):

    pattern = r"(?<=CUSTOMER PO )(.*?)(?=(ROUTE|SHIP))"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).replace('#','').strip()  # Return the captured text, stripped of leading/trailing whitespace and # symbols
    else:
        return None  # Return None if the pattern is not found

def extract_orderNo(text):

    pattern = r"\s+(\d{7}-\d+|T\d{6}-\d+|\d{7} \d+|\d{9})\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found
    
def extract_orderNoDSD(text):

    pattern = r"\s+(\d{7})\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found
    
def extract_BOLtransferNo(text):

    pattern = r"\s+(\d{6}-\d+|\d{6} \d+|\d{6})\s+"
    
    # Search for the pattern in the given text
    match = re.findall(pattern, text, re.IGNORECASE)
    
    if match:
        return match # Return the captured text matches
    else:
        return None  # Return None if the pattern is not found
    
def extract_BOLorderNo(text):

    #pattern = r"\s+(\d{7}-\d{2}|T\d{6}-\d{2})"
    pattern = r"\s+(\d{7}-\d+|T\d{6}-\d+|\d{7} \d+|\d{9})\s+"
    
    # Search for the pattern in the given text
    match = re.findall(pattern, text, re.IGNORECASE)
    
    if match:
        return match # Return the captured text matches
    else:
        return None  # Return None if the pattern is not found
    
def extract_transferNo(text):

    pattern = r"\s+(\d{6}-\d+|\d{6} \d+|\d{6})\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found
    
def extract_serviceNo(text):
    # Regular expression to find text between "ORDER #" and the next space
    pattern = r"\s+(S\d{9})\s+"
    
    # Search for the pattern in the given text
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()  # Return the captured text, stripped of leading/trailing whitespace
    else:
        return None  # Return None if the pattern is not found
    
def clear_directory(directory_path):
     # List all files in the directory
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        
        # Check if it's a file and not a directory
        if os.path.isfile(file_path):
            os.remove(file_path)  # Delete the file

def split_pdf(input_pdf_path, output_folder):
    # Open the input PDF file
    with open(input_pdf_path, 'rb') as input_pdf:
        # Create a PdfReader object
        pdf_reader = PyPDF2.PdfReader(input_pdf)

        # Get the total number of pages in the input PDF
        num_pages = len(pdf_reader.pages)

        # Iterate over each page and create a separate PDF file
        for page_num in range(num_pages):
            pdf_writer = PyPDF2.PdfWriter()

            # Add the page to the writer
            pdf_writer.add_page(pdf_reader.pages[page_num])

            # Define the output file path
            output_pdf_path = f"{output_folder}/page_{page_num + 1}.pdf"

            # Write the page to a new PDF file
            with open(output_pdf_path, 'wb') as output_pdf:
                pdf_writer.write(output_pdf)


def file_to_base64(file_path):
    try:
        with open(file_path, "rb") as file:
            file_content = file.read()
            base64_encoded = base64.b64encode(file_content).decode('utf-8')
            return base64_encoded
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except Exception as e:
         print(f"An error occurred: {e}")
         return None

def create_payload_OE(pono,custno,orderno_full,sro_num,base_64_file):
    ref_orderno_full = orderno_full.replace(" ","-")
    if len(ref_orderno_full) == 9 and "-" not in ref_orderno_full: ref_orderno_full = ref_orderno_full[0:7]+"-"+ref_orderno_full[-2:]
    split = ref_orderno_full.split("-")
    orderno = split[0]
    ordersuf = split[1]
    if orderno[0] == "T": orderno = "1" + orderno[1:]
    if len(ordersuf) == 1: ordersuf = "0" + ordersuf
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Customer_Number",
                        "value": custno
                    },
                    {
                        "name": "Purchase_Order_Number",
                        "value": pono
                    },
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "Order_Number",
                        "value": orderno
                    },
                    {
                        "name": "Order_Suffix",
                        "value": ordersuf
                    },
                    {
                        "name": "Service_Order_Number",
                        "value": sro_num
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": orderno_full+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Pick_List"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_WT(transferno,base_64_file):
    transferno = transferno.replace(" ","-")
    # Check if second-to-last character is '0'
    if len(transferno) > 6 and transferno[-2] == '0':
        # Remove the second-to-last character
        transferno = transferno[:-2] + transferno[-1]
    elif len(transferno) <= 6:
        transferno = transferno + "-0"
    transferno = transferno.split('-')
    
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "Warehouse_Transfer_Number",
                        "value": transferno[0]
                    },
                    {
                        "name": "Warehouse_Transfer_Suffix",
                        "value": transferno[1]
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": transferno[0]+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Warehouse_Transfer_Pick_Ticket"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_BOL(orderno_full,base_64_file):
    
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    }
                ]
            },
            "colls": {
                "name": "Order_Number",
                "coll": []
            },
            "resrs": {
                "res": [
                    {
                        "filename": orderno_full[0]+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Bill_of_Lading"
        }
    }

    for orderno in orderno_full:
        orderno = orderno.replace(" ","-")
        if len(orderno) == 9 and "-" not in orderno: orderno = orderno[0:7]+"-"+orderno[-2:]
        if orderno[0] == "T": orderno = "1" + orderno[1:]
        # Check if second-to-last character is '0'
        if len(orderno) > 6 and orderno[-2] == '0':
            # Remove the second-to-last character
            orderno = orderno[:-2] + orderno[-1]
        elif len(orderno) <= 6:
            orderno = orderno + "-0"
        order_entry = {
            "entityName": "Order_Number",
            "attrs": {
                "attr": [
                    {
                        "name": "Order_Number",
                        "value": orderno
                    }
                ]
            }
        }

        data["item"]["colls"]["coll"].append(order_entry)

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_OTBI(sro_num,custno,base_64_file):
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "SroNum",
                        "value": sro_num
                    },
                    {
                        "name": "CustNum",
                        "value": custno
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": sro_num+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "ISM_OrderToBeInvoiced"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_PR(transferno,base_64_file):
    transferno = transferno.replace(" ","-")
    # Check if second-to-last character is '0'
    if len(transferno) >= 2 and transferno[-2] == '0':
        # Remove the second-to-last character
        transferno = transferno[:-2] + transferno[-1]
    transferno = transferno.split('-')
    
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "Purchase_Order_Number",
                        "value": transferno[0]
                    },
                    {
                        "name": "Purchase_Order_Suffix",
                        "value": transferno[1]
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": transferno[0]+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Pre_Receiving_Report"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_PL(transferno,base_64_file):
    transferno = transferno.replace(" ","-")
    # Check if second-to-last character is '0'
    if len(transferno) > 6 and transferno[-2] == '0':
        # Remove the second-to-last character
        transferno = transferno[:-2] + transferno[-1]
    elif len(transferno) <= 6:
        transferno = transferno + "-0"
    transferno = transferno.split('-')
    
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "Purchase_Order_Number",
                        "value": transferno[0]
                    },
                    {
                        "name": "Purchase_Order_Suffix",
                        "value": transferno[1]
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": transferno[0]+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Pack_List"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def create_payload_DSD(orderno,base_64_file):
    # Constructing the JSON structure
    data = {
        "item": {
            "attrs": {
                "attr": [
                    {
                        "name": "Company_Number",
                        "value": "1"
                    },
                    {
                        "name": "Order_Number",
                        "value": orderno
                    }
                ]
            },
            "resrs": {
                "res": [
                    {
                        "filename": orderno+".pdf",
                        "base64": base_64_file
                    }
                ]
            },
            "acl": {
                "name": "Public"
            },
            "entityName": "Delivery_Invoice"
        }
    }

    # Convert to JSON string (for the API request)
    return json.dumps(data)

def send_request(body):
    # Create a session and send a request for the access token
    token_body = {
        "grant_type": "password", 
        "username": saak,
        "password": sask,
        "client_id": client_id,
        "client_secret": client_secret
    }

    # Make a POST request to get the access token
    response = requests.post(token_url, data=token_body, auth=HTTPBasicAuth(client_id, client_secret))

    if response.status_code == 200:
        token = response.json().get("access_token")
    else:
        print("Failed to get access token:", response.status_code, response.text)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.post(api_url, headers=headers, data=body)

    # return the response code
    return response.status_code


if __name__ == "__main__":
    main()