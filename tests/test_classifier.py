from ocr_uploader.classifier import classify_text

def test_classifier():
    assert classify_text("This is an invoice") == "Invoice"
    assert classify_text("Pick Ticket ABC123") == "Pick Ticket"
    assert classify_text("BILL OF LADING") == "BOL"
    assert classify_text("Random content") == "Unknown"
