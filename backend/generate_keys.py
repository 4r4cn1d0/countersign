"""Generate RSA key pair for JWT signing."""

import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def generate_rsa_key_pair(
    private_key_path: str = "keys/jwt_private.pem",
    public_key_path: str = "keys/jwt_public.pem",
    key_size: int = 2048
):
    """
    Generate RSA key pair for JWT signing.
    
    Args:
        private_key_path: Path to save private key
        public_key_path: Path to save public key
        key_size: RSA key size in bits (default 2048)
    """
    # Create keys directory if it doesn't exist
    os.makedirs(os.path.dirname(private_key_path), exist_ok=True)
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )
    
    # Generate public key
    public_key = private_key.public_key()
    
    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # Write keys to files
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)
    
    with open(public_key_path, 'wb') as f:
        f.write(public_pem)
    
    print(f"✓ RSA key pair generated successfully")
    print(f"  Private key: {private_key_path}")
    print(f"  Public key: {public_key_path}")
    print(f"  Key size: {key_size} bits")
    print(f"\n⚠️  Keep the private key secure and never commit it to version control!")


if __name__ == "__main__":
    generate_rsa_key_pair()
