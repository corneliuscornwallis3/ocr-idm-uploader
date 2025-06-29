from cryptography.fernet import Fernet
import json

client_secret = ""
saak = ""
sask = ""

def encrypt_secret(client_secret,saak,sask):
    key = Fernet.generate_key()
    with open("secret.key","wb") as key_file:
        key_file.write(key)

    with open("secret.key","rb") as key_file:
        key = key_file.read()
    f = Fernet(key)

    credentials = {"client_secret" : client_secret,
    "saak" : saak, 
    "sask" : sask}
    encrypted_credentials = f.encrypt(json.dumps(credentials).encode())

    with open("credentials.enc", "wb") as encrypted_file:
        encrypted_file.write(encrypted_credentials)

encrypt_secret(client_secret,saak,sask)
