from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15
import base64


class CryptoTools:
	def __init__(self,):
		'''
		    Initialize the CryptoTools class.
			https://www.pycryptodome.org/src/signature/pkcs1_v1_5
		'''
		pass
	
	def load_public_key(self, key):
		"""Loads the private key from a text."""
		key_bytes = key.encode()
		return RSA.import_key(key_bytes)
	
	def create_digest(self, data: str) -> bytes:
		"""Creates a SHA-256 digest of the data."""
		return SHA256.new(data.encode())
	
	def signature_valid(self, public_key, signature, data):
		"""Verifies the signature using the provided public key."""
		signature_bytes = base64.b64decode(signature)
		
		try:
			pkcs1_15.new(public_key).verify(data, signature_bytes)
			return True
		except (ValueError, TypeError):
			return False
