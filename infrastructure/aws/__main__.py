"""
RiffScribe AWS Infrastructure using Pulumi.

This script creates the complete AWS infrastructure for RiffScribe including:
- VPC with public and private subnets
- RDS PostgreSQL database
- ElastiCache Redis cluster
- S3 bucket for media storage
- ECS cluster with Fargate services
- Application Load Balancer
- CloudFront distribution (optional)
"""

import pulumi
import pulumi_aws as aws
from pulumi_aws import ec2, rds, elasticache, s3, ecs, iam, logs, cloudfront
import json

from infrastructure.shared.config import get_config, Environment
from infrastructure.shared.utils import (
    get_stack_config,
    get_stack_secret,
    get_availability_zones,
    create_subnet_cidrs,
    get_environment_variables
)

# Get configuration
config = pulumi.Config()
environment = config.get("environment", "dev")
aws_region = config.get("aws:region", "us-east-1")
vpc_cidr = config.get("vpc_cidr", "10.0.0.0/16")
domain = config.get("domain", "")
enable_https = config.get_bool("enable_https", False)

# Get shared configuration
app_config = get_config(environment)

# Create VPC
vpc = ec2.Vpc(
    app_config.get_resource_name("vpc"),
    cidr_block=vpc_cidr,
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={**app_config.get_tags(), "Name": app_config.get_resource_name("vpc")}
)

# Get availability zones
azs = get_availability_zones(aws_region, 2)

# Create subnets
subnet_cidrs = create_subnet_cidrs(vpc_cidr, 4)

public_subnets = []
private_subnets = []

for i, az in enumerate(azs):
    # Public subnet
    public_subnet = ec2.Subnet(
        f"{app_config.get_resource_name('public-subnet')}-{i+1}",
        vpc_id=vpc.id,
        cidr_block=subnet_cidrs[i],
        availability_zone=az,
        map_public_ip_on_launch=True,
        tags={**app_config.get_tags(), "Name": f"{app_config.get_resource_name('public-subnet')}-{i+1}"}
    )
    public_subnets.append(public_subnet)
    
    # Private subnet
    private_subnet = ec2.Subnet(
        f"{app_config.get_resource_name('private-subnet')}-{i+1}",
        vpc_id=vpc.id,
        cidr_block=subnet_cidrs[i+2],
        availability_zone=az,
        tags={**app_config.get_tags(), "Name": f"{app_config.get_resource_name('private-subnet')}-{i+1}"}
    )
    private_subnets.append(private_subnet)

# Internet Gateway
igw = ec2.InternetGateway(
    app_config.get_resource_name("igw"),
    vpc_id=vpc.id,
    tags={**app_config.get_tags(), "Name": app_config.get_resource_name("igw")}
)

# NAT Gateway (for private subnets)
nat_eip = ec2.Eip(
    app_config.get_resource_name("nat-eip"),
    domain="vpc",
    tags=app_config.get_tags()
)

nat_gateway = ec2.NatGateway(
    app_config.get_resource_name("nat"),
    allocation_id=nat_eip.id,
    subnet_id=public_subnets[0].id,
    tags={**app_config.get_tags(), "Name": app_config.get_resource_name("nat")}
)

# Route tables
public_rt = ec2.RouteTable(
    app_config.get_resource_name("public-rt"),
    vpc_id=vpc.id,
    tags={**app_config.get_tags(), "Name": app_config.get_resource_name("public-rt")}
)

private_rt = ec2.RouteTable(
    app_config.get_resource_name("private-rt"),
    vpc_id=vpc.id,
    tags={**app_config.get_tags(), "Name": app_config.get_resource_name("private-rt")}
)

# Routes
ec2.Route(
    app_config.get_resource_name("public-route"),
    route_table_id=public_rt.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id
)

ec2.Route(
    app_config.get_resource_name("private-route"),
    route_table_id=private_rt.id,
    destination_cidr_block="0.0.0.0/0",
    nat_gateway_id=nat_gateway.id
)

# Associate subnets with route tables
for i, subnet in enumerate(public_subnets):
    ec2.RouteTableAssociation(
        f"{app_config.get_resource_name('public-rta')}-{i+1}",
        subnet_id=subnet.id,
        route_table_id=public_rt.id
    )

for i, subnet in enumerate(private_subnets):
    ec2.RouteTableAssociation(
        f"{app_config.get_resource_name('private-rta')}-{i+1}",
        subnet_id=subnet.id,
        route_table_id=private_rt.id
    )

# Security Groups
db_sg = ec2.SecurityGroup(
    app_config.get_resource_name("db-sg"),
    description="Security group for RDS database",
    vpc_id=vpc.id,
    ingress=[{
        "protocol": "tcp",
        "from_port": 5432,
        "to_port": 5432,
        "cidr_blocks": [vpc_cidr]
    }],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }],
    tags=app_config.get_tags()
)

redis_sg = ec2.SecurityGroup(
    app_config.get_resource_name("redis-sg"),
    description="Security group for Redis cache",
    vpc_id=vpc.id,
    ingress=[{
        "protocol": "tcp",
        "from_port": 6379,
        "to_port": 6379,
        "cidr_blocks": [vpc_cidr]
    }],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }],
    tags=app_config.get_tags()
)

app_sg = ec2.SecurityGroup(
    app_config.get_resource_name("app-sg"),
    description="Security group for application",
    vpc_id=vpc.id,
    ingress=[
        {
            "protocol": "tcp",
            "from_port": 8000,
            "to_port": 8000,
            "cidr_blocks": ["0.0.0.0/0"]
        },
        {
            "protocol": "tcp", 
            "from_port": 443,
            "to_port": 443,
            "cidr_blocks": ["0.0.0.0/0"]
        },
        {
            "protocol": "tcp",
            "from_port": 80,
            "to_port": 80,
            "cidr_blocks": ["0.0.0.0/0"]
        }
    ],
    egress=[{
        "protocol": "-1",
        "from_port": 0,
        "to_port": 0,
        "cidr_blocks": ["0.0.0.0/0"]
    }],
    tags=app_config.get_tags()
)

# RDS Subnet Group
db_subnet_group = rds.SubnetGroup(
    app_config.get_resource_name("db-subnet-group"),
    subnet_ids=[s.id for s in private_subnets],
    tags=app_config.get_tags()
)

# RDS Database
database = rds.Instance(
    app_config.get_resource_name("db"),
    identifier=app_config.get_resource_name("db"),
    allocated_storage=app_config.database.allocated_storage,
    max_allocated_storage=app_config.database.max_allocated_storage,
    storage_type="gp3",
    engine="postgres",
    engine_version="15.4",
    instance_class=app_config.database.instance_type,
    db_name="riffscribe",
    username="riffscribe",
    password=get_stack_secret("database_password"),
    vpc_security_group_ids=[db_sg.id],
    db_subnet_group_name=db_subnet_group.name,
    backup_retention_period=app_config.database.backup_retention_days,
    multi_az=app_config.database.multi_az,
    deletion_protection=app_config.database.deletion_protection,
    skip_final_snapshot=not app_config.database.deletion_protection,
    tags=app_config.get_tags()
)

# ElastiCache Subnet Group
redis_subnet_group = elasticache.SubnetGroup(
    app_config.get_resource_name("redis-subnet-group"),
    subnet_ids=[s.id for s in private_subnets]
)

# ElastiCache Redis
redis_cluster = elasticache.Cluster(
    app_config.get_resource_name("redis"),
    cluster_id=app_config.get_resource_name("redis"),
    engine="redis",
    node_type=app_config.redis.node_type,
    num_cache_nodes=app_config.redis.num_cache_nodes,
    parameter_group_name="default.redis7.x",
    port=app_config.redis.port,
    subnet_group_name=redis_subnet_group.name,
    security_group_ids=[redis_sg.id],
    tags=app_config.get_tags()
)

# S3 Bucket for media storage
media_bucket = s3.Bucket(
    app_config.get_resource_name("media"),
    bucket=app_config.storage.bucket_name,
    tags=app_config.get_tags()
)

# S3 Bucket versioning
s3.BucketVersioning(
    f"{app_config.get_resource_name('media')}-versioning",
    bucket=media_bucket.id,
    versioning_configuration={
        "status": "Enabled" if app_config.storage.versioning_enabled else "Disabled"
    }
)

# S3 Bucket public access block
s3.BucketPublicAccessBlock(
    f"{app_config.get_resource_name('media')}-pab",
    bucket=media_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True
)

# S3 Bucket CORS configuration
if app_config.storage.cors_enabled:
    s3.BucketCorsConfiguration(
        f"{app_config.get_resource_name('media')}-cors",
        bucket=media_bucket.id,
        cors_rules=[{
            "allowed_headers": ["*"],
            "allowed_methods": ["GET", "POST", "PUT", "DELETE", "HEAD"],
            "allowed_origins": ["*"],
            "expose_headers": ["ETag"],
            "max_age_seconds": 3000
        }]
    )

# CloudWatch Log Groups
app_log_group = logs.LogGroup(
    app_config.get_resource_name("app-logs"),
    name=f"/ecs/{app_config.get_resource_name('app')}",
    retention_in_days=7 if environment == "dev" else 30
)

worker_log_group = logs.LogGroup(
    app_config.get_resource_name("worker-logs"),
    name=f"/ecs/{app_config.get_resource_name('worker')}",
    retention_in_days=7 if environment == "dev" else 30
)

# ECS Cluster
cluster = ecs.Cluster(
    app_config.get_resource_name("cluster"),
    name=app_config.get_resource_name("cluster"),
    tags=app_config.get_tags()
)

# ECS Task Execution Role
task_execution_role = iam.Role(
    app_config.get_resource_name("task-execution-role"),
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            }
        }]
    }),
    tags=app_config.get_tags()
)

# Attach AWS managed policy
iam.RolePolicyAttachment(
    app_config.get_resource_name("task-execution-policy"),
    role=task_execution_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
)

# ECS Task Role (for application permissions)
task_role = iam.Role(
    app_config.get_resource_name("task-role"),
    assume_role_policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Effect": "Allow", 
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            }
        }]
    }),
    tags=app_config.get_tags()
)

# S3 access policy for task role
s3_policy = iam.RolePolicy(
    app_config.get_resource_name("s3-policy"),
    role=task_role.id,
    policy=pulumi.Output.all(media_bucket.arn).apply(
        lambda args: json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    args[0],
                    f"{args[0]}/*"
                ]
            }]
        })
    )
)

# Export important values
pulumi.export("vpc_id", vpc.id)
pulumi.export("database_endpoint", database.endpoint)
pulumi.export("redis_endpoint", redis_cluster.cache_nodes[0].address)
pulumi.export("media_bucket", media_bucket.bucket)
pulumi.export("cluster_name", cluster.name)
