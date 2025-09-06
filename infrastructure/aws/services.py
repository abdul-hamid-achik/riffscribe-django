"""
ECS Services for RiffScribe application components.
This module defines the ECS task definitions and services for:
- Django web application
- Celery workers
- Celery beat scheduler
"""

import pulumi
import pulumi_aws as aws
from pulumi_aws import ecs, elasticloadbalancingv2 as elbv2, route53, acm
import json

from infrastructure.shared.config import get_config
from infrastructure.shared.utils import get_stack_config, get_stack_secret


def create_load_balancer(vpc_id, public_subnets, app_sg, app_config, domain="", enable_https=False):
    """Create Application Load Balancer"""
    
    # Application Load Balancer
    alb = elbv2.LoadBalancer(
        app_config.get_resource_name("alb"),
        load_balancer_type="application",
        subnets=[s.id for s in public_subnets],
        security_groups=[app_sg.id],
        tags=app_config.get_tags()
    )
    
    # Target Group
    target_group = elbv2.TargetGroup(
        app_config.get_resource_name("tg"),
        port=8000,
        protocol="HTTP",
        vpc_id=vpc_id,
        target_type="ip",
        health_check={
            "enabled": True,
            "path": "/health/",
            "protocol": "HTTP",
            "port": "8000",
            "healthy_threshold": 2,
            "unhealthy_threshold": 2,
            "timeout": 5,
            "interval": 30,
            "matcher": "200"
        },
        tags=app_config.get_tags()
    )
    
    # HTTP Listener
    http_listener = elbv2.Listener(
        app_config.get_resource_name("http-listener"),
        load_balancer_arn=alb.arn,
        port="80",
        protocol="HTTP",
        default_actions=[{
            "type": "forward",
            "target_group_arn": target_group.arn
        }] if not enable_https else [{
            "type": "redirect",
            "redirect": {
                "port": "443",
                "protocol": "HTTPS",
                "status_code": "HTTP_301"
            }
        }]
    )
    
    # HTTPS Listener (if SSL is enabled)
    if enable_https and domain:
        # SSL Certificate (you'd need to create this in ACM first)
        https_listener = elbv2.Listener(
            app_config.get_resource_name("https-listener"),
            load_balancer_arn=alb.arn,
            port="443",
            protocol="HTTPS",
            ssl_policy="ELBSecurityPolicy-TLS-1-2-2017-01",
            certificate_arn=get_stack_config("ssl_certificate_arn"),
            default_actions=[{
                "type": "forward",
                "target_group_arn": target_group.arn
            }]
        )
    
    return alb, target_group


def create_django_service(cluster, app_config, vpc_id, private_subnets, app_sg, 
                         target_group, task_execution_role, task_role,
                         database, redis_cluster, media_bucket, log_group):
    """Create Django web application ECS service"""
    
    # Environment variables
    environment = [
        {"name": "DJANGO_SETTINGS_MODULE", "value": "riffscribe.settings"},
        {"name": "PYTHONPATH", "value": "/app"},
        {"name": "USE_S3", "value": "true"},
        {"name": "AWS_STORAGE_BUCKET_NAME", "value": media_bucket.bucket},
        {"name": "AWS_S3_REGION_NAME", "value": get_stack_config("aws:region", "us-east-1")},
        {"name": "DEBUG", "value": get_stack_config("debug", "false")},
        {"name": "ALLOWED_HOSTS", "value": get_stack_config("allowed_hosts", "*")},
    ]
    
    # Secret environment variables
    secrets = [
        {"name": "DJANGO_SECRET_KEY", "valueFrom": get_stack_secret("django_secret_key")},
        {"name": "OPENAI_API_KEY", "valueFrom": get_stack_secret("openai_api_key")},
    ]
    
    # Build database URL from RDS instance
    database_url = pulumi.Output.all(
        database.endpoint, 
        database.username,
        get_stack_secret("database_password"),
        database.db_name
    ).apply(lambda args: f"postgresql://{args[1]}:{args[2]}@{args[0]}/{args[3]}")
    
    # Build Redis URL from ElastiCache
    redis_url = redis_cluster.cache_nodes[0].address.apply(
        lambda addr: f"redis://{addr}:6379/0"
    )
    
    # Task Definition
    task_definition = ecs.TaskDefinition(
        app_config.get_resource_name("django-task"),
        family=app_config.get_resource_name("django"),
        cpu=str(app_config.compute.cpu),
        memory=str(app_config.compute.memory),
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=task_execution_role.arn,
        task_role_arn=task_role.arn,
        container_definitions=pulumi.Output.all(database_url, redis_url).apply(
            lambda urls: json.dumps([{
                "name": "django-app",
                "image": "your-registry/riffscribe:latest",  # You'll need to build and push this
                "cpu": app_config.compute.cpu,
                "memory": app_config.compute.memory,
                "essential": True,
                "portMappings": [{
                    "containerPort": 8000,
                    "protocol": "tcp"
                }],
                "environment": environment + [
                    {"name": "DATABASE_URL", "value": urls[0]},
                    {"name": "CELERY_BROKER_URL", "value": urls[1]},
                    {"name": "CELERY_RESULT_BACKEND", "value": urls[1]},
                ],
                "secrets": secrets,
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": log_group.name,
                        "awslogs-region": get_stack_config("aws:region", "us-east-1"),
                        "awslogs-stream-prefix": "django"
                    }
                },
                "command": ["gunicorn", "--bind", "0.0.0.0:8000", "riffscribe.wsgi:application"]
            }])
        ),
        tags=app_config.get_tags()
    )
    
    # ECS Service
    service = ecs.Service(
        app_config.get_resource_name("django-service"),
        cluster=cluster.id,
        task_definition=task_definition.arn,
        desired_count=app_config.compute.desired_count,
        launch_type="FARGATE",
        network_configuration={
            "subnets": [s.id for s in private_subnets],
            "security_groups": [app_sg.id],
            "assign_public_ip": False
        },
        load_balancers=[{
            "target_group_arn": target_group.arn,
            "container_name": "django-app",
            "container_port": 8000
        }],
        depends_on=[target_group],
        tags=app_config.get_tags()
    )
    
    return service, task_definition


def create_celery_worker_service(cluster, app_config, vpc_id, private_subnets, app_sg,
                               task_execution_role, task_role, database, redis_cluster, 
                               media_bucket, log_group):
    """Create Celery worker ECS service"""
    
    # Environment variables (similar to Django but without port mapping)
    environment = [
        {"name": "DJANGO_SETTINGS_MODULE", "value": "riffscribe.settings"},
        {"name": "PYTHONPATH", "value": "/app"},
        {"name": "USE_S3", "value": "true"},
        {"name": "AWS_STORAGE_BUCKET_NAME", "value": media_bucket.bucket},
        {"name": "AWS_S3_REGION_NAME", "value": get_stack_config("aws:region", "us-east-1")},
    ]
    
    secrets = [
        {"name": "DJANGO_SECRET_KEY", "valueFrom": get_stack_secret("django_secret_key")},
        {"name": "OPENAI_API_KEY", "valueFrom": get_stack_secret("openai_api_key")},
    ]
    
    database_url = pulumi.Output.all(
        database.endpoint, 
        database.username,
        get_stack_secret("database_password"),
        database.db_name
    ).apply(lambda args: f"postgresql://{args[1]}:{args[2]}@{args[0]}/{args[3]}")
    
    redis_url = redis_cluster.cache_nodes[0].address.apply(
        lambda addr: f"redis://{addr}:6379/0"
    )
    
    # Task Definition for Celery Worker
    task_definition = ecs.TaskDefinition(
        app_config.get_resource_name("worker-task"),
        family=app_config.get_resource_name("worker"),
        cpu=str(app_config.compute.cpu),
        memory=str(app_config.compute.memory),
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=task_execution_role.arn,
        task_role_arn=task_role.arn,
        container_definitions=pulumi.Output.all(database_url, redis_url).apply(
            lambda urls: json.dumps([{
                "name": "celery-worker",
                "image": "your-registry/riffscribe:latest",
                "cpu": app_config.compute.cpu,
                "memory": app_config.compute.memory,
                "essential": True,
                "environment": environment + [
                    {"name": "DATABASE_URL", "value": urls[0]},
                    {"name": "CELERY_BROKER_URL", "value": urls[1]},
                    {"name": "CELERY_RESULT_BACKEND", "value": urls[1]},
                ],
                "secrets": secrets,
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": log_group.name,
                        "awslogs-region": get_stack_config("aws:region", "us-east-1"),
                        "awslogs-stream-prefix": "worker"
                    }
                },
                "command": ["celery", "-A", "riffscribe", "worker", "-l", "info", "--concurrency=1"]
            }])
        ),
        tags=app_config.get_tags()
    )
    
    # ECS Service for Workers
    service = ecs.Service(
        app_config.get_resource_name("worker-service"),
        cluster=cluster.id,
        task_definition=task_definition.arn,
        desired_count=1,  # Usually fewer workers than web instances
        launch_type="FARGATE",
        network_configuration={
            "subnets": [s.id for s in private_subnets],
            "security_groups": [app_sg.id],
            "assign_public_ip": False
        },
        tags=app_config.get_tags()
    )
    
    return service, task_definition


def create_celery_beat_service(cluster, app_config, vpc_id, private_subnets, app_sg,
                             task_execution_role, task_role, database, redis_cluster, 
                             media_bucket, log_group):
    """Create Celery beat scheduler ECS service"""
    
    # Similar to worker but with beat command and only 1 instance
    environment = [
        {"name": "DJANGO_SETTINGS_MODULE", "value": "riffscribe.settings"},
        {"name": "PYTHONPATH", "value": "/app"},
        {"name": "USE_S3", "value": "true"},
        {"name": "AWS_STORAGE_BUCKET_NAME", "value": media_bucket.bucket},
        {"name": "AWS_S3_REGION_NAME", "value": get_stack_config("aws:region", "us-east-1")},
    ]
    
    secrets = [
        {"name": "DJANGO_SECRET_KEY", "valueFrom": get_stack_secret("django_secret_key")},
    ]
    
    database_url = pulumi.Output.all(
        database.endpoint, 
        database.username,
        get_stack_secret("database_password"),
        database.db_name
    ).apply(lambda args: f"postgresql://{args[1]}:{args[2]}@{args[0]}/{args[3]}")
    
    redis_url = redis_cluster.cache_nodes[0].address.apply(
        lambda addr: f"redis://{addr}:6379/0"
    )
    
    # Task Definition for Celery Beat
    task_definition = ecs.TaskDefinition(
        app_config.get_resource_name("beat-task"),
        family=app_config.get_resource_name("beat"),
        cpu="512",
        memory="1024", 
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        execution_role_arn=task_execution_role.arn,
        task_role_arn=task_role.arn,
        container_definitions=pulumi.Output.all(database_url, redis_url).apply(
            lambda urls: json.dumps([{
                "name": "celery-beat",
                "image": "your-registry/riffscribe:latest",
                "cpu": 512,
                "memory": 1024,
                "essential": True,
                "environment": environment + [
                    {"name": "DATABASE_URL", "value": urls[0]},
                    {"name": "CELERY_BROKER_URL", "value": urls[1]},
                    {"name": "CELERY_RESULT_BACKEND", "value": urls[1]},
                ],
                "secrets": secrets,
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": log_group.name,
                        "awslogs-region": get_stack_config("aws:region", "us-east-1"),
                        "awslogs-stream-prefix": "beat"
                    }
                },
                "command": ["celery", "-A", "riffscribe", "beat", "-l", "info"]
            }])
        ),
        tags=app_config.get_tags()
    )
    
    # ECS Service for Beat (only 1 instance)
    service = ecs.Service(
        app_config.get_resource_name("beat-service"),
        cluster=cluster.id,
        task_definition=task_definition.arn,
        desired_count=1,  # Only one beat scheduler
        launch_type="FARGATE",
        network_configuration={
            "subnets": [s.id for s in private_subnets],
            "security_groups": [app_sg.id],
            "assign_public_ip": False
        },
        tags=app_config.get_tags()
    )
    
    return service, task_definition
