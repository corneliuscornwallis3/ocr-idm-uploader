def mock_upload(filename, doc_type, content):
    print(f"Uploading '{filename}' as '{doc_type}' with content preview:")
    print(content[:100] + "...\n")
