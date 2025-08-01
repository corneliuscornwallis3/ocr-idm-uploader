def classify_text(text):
    text = text.lower()
    if "invoice" in text:
        return "Invoice"
    elif "pick ticket" in text:
        return "Pick Ticket"
    elif "bill of lading" in text:
        return "BOL"
    return "Unknown"
