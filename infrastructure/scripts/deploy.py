#!/usr/bin/env python3
"""
Deployment script for RiffScribe infrastructure.
This script provides a simplified interface to deploy infrastructure using Pulumi.
"""

import os
import sys
import argparse
import subprocess
import yaml
from pathlib import Path
from typing import Dict, Any


def load_config(config_file: str) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = Path(__file__).parent.parent / "configs" / f"{config_file}.yaml"
    
    if not config_path.exists():
        print(f"Error: Configuration file {config_path} not found")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_command(cmd: list, cwd: str = None) -> bool:
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(cmd)}")
        print(f"Exit code: {e.returncode}")
        print(f"Error output: {e.stderr}")
        return False


def setup_pulumi_stack(environment: str, config: Dict[str, Any]) -> bool:
    """Setup Pulumi stack with configuration for AWS"""
    stack_name = f"riffscribe-aws-{environment}"
    aws_path = Path(__file__).parent.parent / "aws"
    
    # Change to AWS directory
    os.chdir(aws_path)
    
    # Initialize or select stack
    print(f"Setting up Pulumi stack: {stack_name}")
    if not run_command(["pulumi", "stack", "select", stack_name]):
        print("Stack doesn't exist, creating it...")
        if not run_command(["pulumi", "stack", "init", stack_name]):
            return False
    
    # Set configuration values
    print("Setting configuration values...")
    config_commands = [
        ["pulumi", "config", "set", "environment", environment],
        ["pulumi", "config", "set", "aws:region", config["aws"]["region"]],
        ["pulumi", "config", "set", "vpc_cidr", config["aws"]["vpc_cidr"]],
        ["pulumi", "config", "set", "enable_https", str(config["aws"]["enable_https"]).lower()],
    ]
    
    if config["aws"]["domain"]:
        config_commands.append(["pulumi", "config", "set", "domain", config["aws"]["domain"]])
    
    for cmd in config_commands:
        if not run_command(cmd):
            return False
    
    # Set secrets (these should be set manually or via environment variables)
    secrets = [
        "database_password",
        "django_secret_key", 
        "openai_api_key"
    ]
    
    for secret in secrets:
        env_var = secret.upper()
        if env_var in os.environ:
            print(f"Setting secret: {secret}")
            if not run_command(["pulumi", "config", "set", "--secret", secret, os.environ[env_var]]):
                return False
        else:
            print(f"Warning: Environment variable {env_var} not found. You may need to set this secret manually.")
    
    return True


def deploy_infrastructure(environment: str, preview: bool = False) -> bool:
    """Deploy the AWS infrastructure"""
    aws_path = Path(__file__).parent.parent / "aws"
    os.chdir(aws_path)
    
    cmd = ["pulumi", "preview" if preview else "up"]
    if not preview:
        cmd.append("--yes")
    
    print(f"{'Previewing' if preview else 'Deploying'} infrastructure...")
    return run_command(cmd)


def destroy_infrastructure(environment: str) -> bool:
    """Destroy the AWS infrastructure"""
    aws_path = Path(__file__).parent.parent / "aws"
    os.chdir(aws_path)
    
    print("Destroying infrastructure...")
    return run_command(["pulumi", "destroy", "--yes"])


def main():
    parser = argparse.ArgumentParser(description="Deploy RiffScribe infrastructure to AWS")
    parser.add_argument("action", choices=["deploy", "preview", "destroy"], 
                       help="Action to perform")
    parser.add_argument("--environment", "-e", choices=["dev", "staging", "prod"], 
                       default="dev", help="Environment to deploy")
    parser.add_argument("--config", "-c", help="Configuration file (defaults to environment name)")
    
    args = parser.parse_args()
    
    # Load configuration
    config_file = args.config or args.environment
    config = load_config(config_file)
    
    # Setup Pulumi stack
    if not setup_pulumi_stack(args.environment, config):
        print("Failed to setup Pulumi stack")
        sys.exit(1)
    
    # Perform action
    if args.action == "deploy":
        success = deploy_infrastructure(args.environment, preview=False)
    elif args.action == "preview":
        success = deploy_infrastructure(args.environment, preview=True)
    elif args.action == "destroy":
        success = destroy_infrastructure(args.environment)
    
    if not success:
        print(f"Failed to {args.action} infrastructure")
        sys.exit(1)
    
    print(f"Successfully completed {args.action}")


if __name__ == "__main__":
    main()
