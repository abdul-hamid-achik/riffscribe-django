"""
Shared configuration for RiffScribe infrastructure.
This module contains common settings that can be used across different cloud providers.
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class Environment(Enum):
    DEVELOPMENT = "dev"
    STAGING = "staging"
    PRODUCTION = "prod"


@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    instance_type: str
    allocated_storage: int
    max_allocated_storage: int
    backup_retention_days: int
    multi_az: bool
    deletion_protection: bool


@dataclass
class RedisConfig:
    """Redis cache configuration"""
    node_type: str
    num_cache_nodes: int
    parameter_group_family: str
    port: int


@dataclass
class StorageConfig:
    """Object storage configuration"""
    bucket_name: str
    versioning_enabled: bool
    lifecycle_rules_enabled: bool
    cors_enabled: bool


@dataclass
class ComputeConfig:
    """Container/compute configuration"""
    cpu: int
    memory: int
    desired_count: int
    max_capacity: int
    min_capacity: int


class Config:
    """Main configuration class that holds all infrastructure settings"""
    
    def __init__(self, environment: Environment, project_name: str = "riffscribe"):
        self.environment = environment
        self.project_name = project_name
        self._configs = self._load_configs()
    
    def _load_configs(self) -> Dict[str, Any]:
        """Load environment-specific configurations"""
        configs = {
            Environment.DEVELOPMENT: {
                "database": DatabaseConfig(
                    instance_type="db.t3.micro",
                    allocated_storage=20,
                    max_allocated_storage=100,
                    backup_retention_days=7,
                    multi_az=False,
                    deletion_protection=False
                ),
                "redis": RedisConfig(
                    node_type="cache.t3.micro",
                    num_cache_nodes=1,
                    parameter_group_family="redis7.x",
                    port=6379
                ),
                "storage": StorageConfig(
                    bucket_name=f"{self.project_name}-media-dev",
                    versioning_enabled=False,
                    lifecycle_rules_enabled=False,
                    cors_enabled=True
                ),
                "compute": ComputeConfig(
                    cpu=512,
                    memory=1024,
                    desired_count=1,
                    max_capacity=2,
                    min_capacity=1
                )
            },
            Environment.STAGING: {
                "database": DatabaseConfig(
                    instance_type="db.t3.small",
                    allocated_storage=50,
                    max_allocated_storage=200,
                    backup_retention_days=14,
                    multi_az=False,
                    deletion_protection=True
                ),
                "redis": RedisConfig(
                    node_type="cache.t3.small",
                    num_cache_nodes=1,
                    parameter_group_family="redis7.x",
                    port=6379
                ),
                "storage": StorageConfig(
                    bucket_name=f"{self.project_name}-media-staging",
                    versioning_enabled=True,
                    lifecycle_rules_enabled=True,
                    cors_enabled=True
                ),
                "compute": ComputeConfig(
                    cpu=1024,
                    memory=2048,
                    desired_count=1,
                    max_capacity=3,
                    min_capacity=1
                )
            },
            Environment.PRODUCTION: {
                "database": DatabaseConfig(
                    instance_type="db.t3.medium",
                    allocated_storage=100,
                    max_allocated_storage=500,
                    backup_retention_days=30,
                    multi_az=True,
                    deletion_protection=True
                ),
                "redis": RedisConfig(
                    node_type="cache.t3.medium",
                    num_cache_nodes=2,
                    parameter_group_family="redis7.x",
                    port=6379
                ),
                "storage": StorageConfig(
                    bucket_name=f"{self.project_name}-media-prod",
                    versioning_enabled=True,
                    lifecycle_rules_enabled=True,
                    cors_enabled=True
                ),
                "compute": ComputeConfig(
                    cpu=2048,
                    memory=4096,
                    desired_count=2,
                    max_capacity=10,
                    min_capacity=2
                )
            }
        }
        return configs
    
    @property
    def database(self) -> DatabaseConfig:
        return self._configs[self.environment]["database"]
    
    @property
    def redis(self) -> RedisConfig:
        return self._configs[self.environment]["redis"]
    
    @property
    def storage(self) -> StorageConfig:
        return self._configs[self.environment]["storage"]
    
    @property
    def compute(self) -> ComputeConfig:
        return self._configs[self.environment]["compute"]
    
    def get_resource_name(self, resource_type: str) -> str:
        """Generate a consistent resource name"""
        return f"{self.project_name}-{self.environment.value}-{resource_type}"
    
    def get_tags(self) -> Dict[str, str]:
        """Generate standard tags for all resources"""
        return {
            "Project": self.project_name,
            "Environment": self.environment.value,
            "ManagedBy": "Pulumi",
            "Application": "RiffScribe"
        }


def get_config(environment: str, project_name: str = "riffscribe") -> Config:
    """Factory function to create configuration instance"""
    env = Environment(environment)
    return Config(env, project_name)
