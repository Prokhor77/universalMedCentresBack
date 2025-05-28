from cryptography.fernet import Fernet

FERNET_KEY = b'vvYfxJNatmT36RxbF156vIJxxSIwayOPyv9o76b1vq0='
fernet = Fernet(FERNET_KEY)

plain_text = "ww234igo3bf2fw"
encrypted = fernet.encrypt(plain_text.encode()).decode()

print(encrypted)
