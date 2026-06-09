#!/usr/bin/env python3

"""
Restore data backed up with paperbackup.py
Handles QR code extraction from PDF and optional decryption
"""

import sys
import os
import base64
import hashlib
import getpass
import argparse
from io import BytesIO

# Try to import required libraries
try:
    from pyzbar.pyzbar import decode
    from PIL import Image
    import pdf2image
except ImportError as e:
    print(f"Error: Missing required library. Install with:", file=sys.stderr)
    print("  pip install pyzbar pillow pdf2image", file=sys.stderr)
    print("Also requires: libzbar0 (on Linux) or zbar (on macOS via brew)", file=sys.stderr)
    sys.exit(1)

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography library not found. Install with: pip install cryptography", file=sys.stderr)
    sys.exit(1)


def derive_key_from_password(password, salt=None):
    """Derive encryption key from password using PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    key_material = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    key = base64.urlsafe_b64encode(key_material[:32])
    return key, salt


def decrypt_data(encrypted_data, password):
    """Decrypt data with password. Input should start with 'ENC:'."""
    if not encrypted_data.startswith(b'ENC:'):
        raise ValueError('Data does not start with ENC: marker')
    
    encrypted_data = encrypted_data[4:]
    parts = encrypted_data.split(b':')
    if len(parts) < 2:
        raise ValueError('Invalid encrypted data format')
    
    salt_b64 = parts[0]
    encrypted_msg = b':'.join(parts[1:])
    salt = base64.b64decode(salt_b64)
    key, _ = derive_key_from_password(password, salt)
    f = Fernet(key)
    decrypted = f.decrypt(encrypted_msg)
    return decrypted


def extract_qr_codes_from_pdf(pdf_path):
    """Extract QR code data from PDF file."""
    try:
        # Convert PDF to images
        images = pdf2image.convert_from_path(pdf_path)
    except Exception as e:
        print(f"Error converting PDF to images: {e}", file=sys.stderr)
        sys.exit(1)
    
    qr_data_dict = {}  # Dict to store QR codes by sequence number
    
    # Extract QR codes from each image
    for page_num, image in enumerate(images):
        decoded_objects = decode(image)
        
        for obj in decoded_objects:
            try:
                qr_text = obj.data.decode('utf-8')
                # Parse: ^<number> <data>
                if qr_text.startswith('^'):
                    parts = qr_text.split(' ', 1)
                    seq_str = parts[0][1:]  # Remove '^'
                    seq_num = int(seq_str)
                    data = parts[1] if len(parts) > 1 else ''
                    qr_data_dict[seq_num] = data
                    # print(f"Found QR code #{seq_num} on page {page_num + 1}", file=sys.stderr)
            except (ValueError, UnicodeDecodeError, IndexError) as e:
                print(f"Warning: Could not parse QR code on page {page_num + 1}: {e}", file=sys.stderr)
    
    if not qr_data_dict:
        print("Error: No QR codes found in PDF", file=sys.stderr)
        sys.exit(1)
    
    # Reconstruct data from sorted sequence
    reconstructed_b64 = ''
    for seq_num in sorted(qr_data_dict.keys()):
        reconstructed_b64 += qr_data_dict[seq_num]
    
    return reconstructed_b64


def get_password(pdf_path, password_arg):
    """Get password from argument, file, or prompt."""
    # Check for password file
    pwd_file = f"{pdf_path}.pwd"
    if os.path.isfile(pwd_file):
        try:
            with open(pwd_file, 'r') as f:
                password = f.read().strip()
            print(f"Password loaded from {pwd_file}", file=sys.stderr)
            return password
        except Exception as e:
            print(f"Error reading password file: {e}", file=sys.stderr)
    
    # Check for command-line argument
    if password_arg:
        return password_arg
    
    # Prompt interactively
    password = getpass.getpass('Data is encrypted. Enter password to decrypt: ')
    return password


def main():
    parser = argparse.ArgumentParser(description='Restore data from paperbackup PDF')
    parser.add_argument('pdf_file', help='PDF file created by paperbackup.py')
    parser.add_argument('--password', dest='password', default=None,
                        help='Password for decryption (if not provided, will prompt or read from .pwd file)')
    args = parser.parse_args()
    
    pdf_path = args.pdf_file
    
    if not os.path.isfile(pdf_path):
        print(f"Error: {pdf_path} is not a file", file=sys.stderr)
        sys.exit(1)
    
    # Extract QR codes from PDF
    try:
        encoded_data = extract_qr_codes_from_pdf(pdf_path)
    except Exception as e:
        print(f"Error extracting QR codes: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Decode from base64
    try:
        data_bytes = base64.b64decode(encoded_data)
    except Exception as e:
        print(f"Error decoding base64: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Check if encrypted
    if data_bytes.startswith(b'ENC:'):
        # Get password
        password = get_password(pdf_path, args.password)
        
        if not password:
            print("Error: No password provided for encrypted data", file=sys.stderr)
            sys.exit(1)
        
        # Decrypt
        try:
            data_bytes = decrypt_data(data_bytes, password)
        except Exception as e:
            print(f"Error: Decryption failed. {e}", file=sys.stderr)
            sys.exit(1)
    
    # Output binary data to stdout
    sys.stdout.buffer.write(data_bytes)


if __name__ == '__main__':
    main()
