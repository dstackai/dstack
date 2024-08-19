from dstack._internal.server.services.encryption.keys.aes import (
    AESEncryptionKey,
    AESEncryptionKeyConfig,
)


def get_aes_secret() -> str:
    return "E5yzN6V3XvBq/f085ISWFCdgnOGED0kuFaAkASlmmO4="


class TestAESEncryptionKey:
    def test_encrypts_decrypts(self):
        key = AESEncryptionKey(AESEncryptionKeyConfig(secret=get_aes_secret(), name="key1"))
        plaintext = "This is a test string."
        encrypted_text = key.encrypt(plaintext)
        assert encrypted_text != plaintext
        decrypted_text = key.decrypt(encrypted_text)
        assert decrypted_text == plaintext
