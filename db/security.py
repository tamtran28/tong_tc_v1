
import hashlib
import os

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"

def verify_password(password: str, hashed_value: str) -> bool:
    try:
        salt, hashed = hashed_value.split("$")
        return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
    except:
        return False

def require_role(user, allowed_roles):
    """
    Check user role. allowed_roles: ['admin', 'pos']
    """
    if not user:
        return False

    return user.get("role") in allowed_roles


