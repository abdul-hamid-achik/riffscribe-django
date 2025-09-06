"""
Utility functions for infrastructure management.
"""
import os
import json
from typing import Dict, Any, Optional


def get_stack_config(key: str, default: Optional[str] = None) -> str:
    """Get configuration value from Pulumi stack or environment variables"""
    import pulumi
    
    try:
        # Try to get from Pulumi config first
        config = pulumi.Config()
        return config.get(key) or default
    except:
        # Fallback to environment variables
        return os.getenv(key, default)


def get_stack_secret(key: str) -> Optional[str]:
    """Get secret configuration value from Pulumi stack"""
    import pulumi
    
    try:
        config = pulumi.Config()
        return config.get_secret(key)
    except:
        return None


def load_json_config(file_path: str) -> Dict[str, Any]:
    """Load JSON configuration file"""
    with open(file_path, 'r') as f:
        return json.load(f)


def get_availability_zones(region: str, count: int = 2) -> list:
    """Get availability zones for a given region"""
    # This is a simplified version - in practice, you'd query the cloud provider
    az_mapping = {
        "us-east-1": ["us-east-1a", "us-east-1b", "us-east-1c"],
        "us-west-2": ["us-west-2a", "us-west-2b", "us-west-2c"],
        "eu-west-1": ["eu-west-1a", "eu-west-1b", "eu-west-1c"],
        "ap-southeast-1": ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"],
    }
    
    zones = az_mapping.get(region, [f"{region}a", f"{region}b", f"{region}c"])
    return zones[:count]


def create_subnet_cidrs(vpc_cidr: str, count: int) -> list:
    """Generate subnet CIDRs from VPC CIDR"""
    import ipaddress
    
    network = ipaddress.IPv4Network(vpc_cidr)
    subnet_bits = (count - 1).bit_length()
    subnets = list(network.subnets(new_prefix=network.prefixlen + subnet_bits))
    
    return [str(subnet) for subnet in subnets[:count]]


def get_environment_variables() -> Dict[str, str]:
    """Get standard environment variables for RiffScribe application"""
    return {
        "DJANGO_SETTINGS_MODULE": "riffscribe.settings",
        "PYTHONPATH": "/app",
        "CELERY_BROKER_URL": get_stack_config("redis_url", "redis://localhost:6379/0"),
        "CELERY_RESULT_BACKEND": get_stack_config("redis_url", "redis://localhost:6379/0"),
        "DATABASE_URL": get_stack_config("database_url"),
        "AWS_STORAGE_BUCKET_NAME": get_stack_config("storage_bucket_name"),
        "AWS_S3_REGION_NAME": get_stack_config("aws_region", "us-east-1"),
        "USE_S3": "true",
        "DJANGO_SECRET_KEY": get_stack_secret("django_secret_key"),
        "DEBUG": get_stack_config("debug", "false"),
        "ALLOWED_HOSTS": get_stack_config("allowed_hosts", "localhost,127.0.0.1"),
    }


def generate_password(length: int = 16) -> str:
    """Generate a secure random password"""
    import secrets
    import string
    
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def validate_environment(env: str) -> bool:
    """Validate environment name"""
    valid_envs = ["dev", "staging", "prod"]
    return env in valid_envs
