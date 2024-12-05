import re

def validate_license_key(license_key: str):
    """Validate the format of a license key."""
    pattern = r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){3}$"  # Matches format
    if not re.match(pattern, license_key):
        raise ValueError("Invalid license key format. Ensure it follows 00000-00000-00000-00000 format.")
