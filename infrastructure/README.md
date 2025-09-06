# RiffScribe Infrastructure as Code (AWS)

This directory contains Infrastructure as Code (IaC) configurations for deploying RiffScribe to AWS using [Pulumi](https://www.pulumi.com/) with Python.

## Overview

RiffScribe's AWS infrastructure includes:
- **Web Application**: Django app running on ECS Fargate
- **Background Workers**: Celery workers for audio processing on ECS Fargate
- **Task Scheduler**: Celery beat scheduler on ECS Fargate
- **Database**: Amazon RDS PostgreSQL
- **Cache**: Amazon ElastiCache Redis
- **Storage**: Amazon S3 for audio files and media
- **Load Balancer**: Application Load Balancer for traffic distribution
- **Networking**: VPC with public and private subnets
- **Monitoring**: CloudWatch logs and optional monitoring

## Project Structure

```
infrastructure/
├── README.md              # This file
├── Makefile               # Simplified deployment commands
├── shared/                # Shared modules and utilities
│   ├── config.py          # Environment-specific configurations
│   └── utils.py           # Utility functions
├── aws/                   # AWS infrastructure
│   ├── __main__.py        # Main AWS Pulumi program
│   ├── services.py        # ECS services definitions
│   └── Pulumi.yaml        # AWS Pulumi configuration
├── configs/               # Environment configurations
│   ├── dev.yaml           # Development settings
│   ├── staging.yaml       # Staging settings
│   └── prod.yaml          # Production settings
├── scripts/               # Deployment scripts
│   └── deploy.py          # Main deployment script
└── example.env            # Example environment variables
```

## Prerequisites

### 1. Install Dependencies

First, install the infrastructure dependencies using `uv`:

```bash
# Install infrastructure dependencies
uv sync --extra infrastructure

# Or if you're not using uv
pip install pulumi pulumi-aws
```

### 2. Install Pulumi CLI

Follow the [Pulumi installation guide](https://www.pulumi.com/docs/get-started/install/) for your platform:

```bash
# macOS
brew install pulumi

# Linux
curl -fsSL https://get.pulumi.com | sh

# Windows
winget install pulumi
```

### 3. Set up AWS Credentials

```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### 4. Set up Pulumi Backend

```bash
# Login to Pulumi Cloud (free for individuals)
pulumi login

# Or use local backend
pulumi login --local
```

## Configuration

### Environment Variables

Copy the example environment file and configure it:

```bash
cp infrastructure/example.env infrastructure/.env
# Edit .env with your actual values
```

### Configuration Files

Each environment has its own configuration file in `infrastructure/configs/`:

- `dev.yaml` - Development environment (single AZ, smaller instances)
- `staging.yaml` - Staging environment (production-like setup)
- `prod.yaml` - Production environment (high availability, larger instances)

You can customize these files to match your requirements.

## Quick Start

### 1. Deploy Development Environment

```bash
# Navigate to infrastructure directory
cd infrastructure

# Using the deployment script
python scripts/deploy.py deploy --environment dev

# Or using make (recommended)
make dev-deploy
```

### 2. Preview Changes

```bash
# Preview what will be deployed
python scripts/deploy.py preview --environment dev

# Or using make
make dev-preview
```

### 3. Deploy to Production

```bash
# Deploy production infrastructure
python scripts/deploy.py deploy --environment prod

# Or using make (includes safety confirmation)
make prod-deploy
```

## Manual Deployment

If you prefer to use Pulumi directly:

```bash
cd infrastructure/aws

# Create a new stack
pulumi stack init riffscribe-aws-dev

# Set configuration
pulumi config set aws:region us-east-1
pulumi config set environment dev
pulumi config set vpc_cidr "10.0.0.0/16"
pulumi config set enable_https false

# Set secrets
pulumi config set --secret database_password your_secure_password
pulumi config set --secret django_secret_key your_django_secret_key
pulumi config set --secret openai_api_key your_openai_api_key

# Deploy
pulumi up
```

## Container Images

Before deploying, you need to build and push your Docker images to Amazon ECR or another container registry.

### Creating ECR Repository

```bash
# Create ECR repository
aws ecr create-repository --repository-name riffscribe

# Get login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
```

### Building and Pushing Images

```bash
# Build the main application image
docker build -t riffscribe:latest .

# Tag for ECR
docker tag riffscribe:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/riffscribe:latest

# Push to ECR
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/riffscribe:latest
```

### Update Image References

Update your Pulumi programs to reference your ECR repository:

```python
# In your __main__.py file, update the image reference:
"image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/riffscribe:latest"
```

## Environment-Specific Configurations

### Development (`dev.yaml`)
- Single availability zone deployment
- Smaller RDS instance (db.t3.micro)
- Basic ElastiCache (cache.t3.micro)
- Lower compute resources (512 CPU, 1024 MB memory)
- No HTTPS/SSL
- Cost-optimized settings

### Staging (`staging.yaml`)
- Multi-availability zone for redundancy
- Medium RDS instance (db.t3.small)
- Standard ElastiCache (cache.t3.small)
- Medium compute resources (1024 CPU, 2048 MB memory)
- HTTPS enabled with domain
- Production-like configuration

### Production (`prod.yaml`)
- Multi-availability zone with high availability
- Larger RDS instance (db.t3.medium) with Multi-AZ
- Redis cluster (cache.t3.medium)
- Higher compute resources (2048 CPU, 4096 MB memory)
- HTTPS enforced
- Enhanced monitoring and backup retention

## AWS Resources Created

The infrastructure creates the following AWS resources:

### Networking
- VPC with public and private subnets
- Internet Gateway and NAT Gateway
- Route tables and security groups
- Application Load Balancer

### Compute
- ECS Cluster with Fargate services
- ECS Task Definitions for Django, Celery workers, and beat scheduler
- Auto Scaling Groups

### Database & Cache
- RDS PostgreSQL instance with automated backups
- ElastiCache Redis cluster

### Storage
- S3 bucket for media files with CORS configuration
- CloudWatch Log Groups for container logs

### Security
- IAM roles and policies for ECS tasks
- Security groups for network access control

## Secrets Management

Sensitive configuration is managed through Pulumi's secret system:

```bash
# Set required secrets
pulumi config set --secret database_password your_secure_password
pulumi config set --secret django_secret_key your_django_secret_key
pulumi config set --secret openai_api_key your_openai_api_key

# Optional SSL certificate ARN for HTTPS
pulumi config set ssl_certificate_arn arn:aws:acm:us-east-1:123456789012:certificate/abc123

# View current config (secrets are encrypted)
pulumi config
```

## Custom Domains and SSL

To use a custom domain with HTTPS:

1. **Register your domain** and configure DNS

2. **Request SSL certificate** in AWS Certificate Manager:
   ```bash
   aws acm request-certificate --domain-name yourdomain.com --domain-name *.yourdomain.com --validation-method DNS
   ```

3. **Update your configuration**:
   ```yaml
   aws:
     enable_https: true
     domain: "yourdomain.com"
   ```

4. **Set the SSL certificate ARN**:
   ```bash
   pulumi config set ssl_certificate_arn arn:aws:acm:us-east-1:123456789012:certificate/your-cert-id
   ```

## Scaling Configuration

### Horizontal Scaling
Modify the `compute` section in your environment config:

```yaml
compute:
  desired_count: 2    # Number of running instances
  max_capacity: 10    # Maximum instances for auto-scaling
  min_capacity: 1     # Minimum instances
```

### Vertical Scaling
Update instance resources:

```yaml
compute:
  cpu: 2048          # CPU units (1024 = 1 vCPU)
  memory: 4096       # Memory in MB
```

### Database Scaling
Update database configuration:

```yaml
database:
  instance_type: "db.t3.large"  # Larger instance
  allocated_storage: 200        # More storage
```

## Monitoring and Logging

### CloudWatch Integration
- Container logs automatically sent to CloudWatch
- Application Load Balancer access logs
- RDS Performance Insights (optional)

### Custom Dashboards
You can create CloudWatch dashboards to monitor:
- ECS service health and performance
- RDS database metrics
- Load balancer request metrics
- Application-specific metrics

## Backup and Disaster Recovery

### RDS Automated Backups
- Daily automated backups with configurable retention
- Point-in-time recovery available
- Multi-AZ deployment for high availability (staging/prod)

### S3 Data Protection
- Versioning enabled for media files
- Cross-region replication (optional)
- Lifecycle policies for cost optimization

## Cost Optimization

### Development Environment
- Use spot instances where possible
- Single AZ deployment
- Smaller instance sizes
- Reduced backup retention (7 days)

### Production Environment
- Reserved Instances for predictable workloads
- Auto-scaling based on CPU/memory metrics
- S3 Intelligent Tiering for storage cost optimization
- Regular cost analysis and right-sizing

## Troubleshooting

### Common Issues

1. **ECS Tasks Failing to Start**
   - Check CloudWatch logs for container errors
   - Verify ECR image accessibility
   - Review environment variables and secrets

2. **Database Connection Issues**
   - Verify security group rules allow port 5432
   - Check VPC and subnet configuration
   - Ensure database credentials are correct

3. **Load Balancer Health Check Failures**
   - Verify application responds on health check endpoint (`/health/`)
   - Check security group allows ALB traffic on port 8000
   - Review target group health check configuration

### Debugging Commands

```bash
# View stack outputs
pulumi stack output

# Check logs
pulumi logs

# View ECS service status
aws ecs describe-services --cluster riffscribe-dev-cluster --services riffscribe-dev-django-service

# Check RDS status
aws rds describe-db-instances --db-instance-identifier riffscribe-dev-db

# View CloudWatch logs
aws logs tail /ecs/riffscribe-dev-app --follow
```

## Cleanup

To destroy infrastructure:

```bash
# Using the deploy script
python scripts/deploy.py destroy --environment dev

# Or manually
cd infrastructure/aws
pulumi destroy
```

**Warning**: This will permanently delete all resources. Make sure you have backups of any important data.

## Security Best Practices

1. **Network Security**
   - Database and Redis in private subnets
   - Strict security group rules
   - VPC Flow Logs enabled

2. **Access Control**
   - IAM roles with least privilege principles
   - No hardcoded credentials
   - MFA enabled for AWS console access

3. **Secrets Management**
   - Use Pulumi secrets for sensitive data
   - Rotate passwords regularly
   - Enable encryption at rest and in transit

4. **Monitoring**
   - CloudTrail for API logging
   - GuardDuty for threat detection
   - Config for compliance monitoring

## Performance Tuning

### Application Performance
- Use Application Load Balancer for SSL termination
- Enable ECS service auto-scaling
- Configure appropriate health checks

### Database Performance
- Use RDS Performance Insights
- Enable enhanced monitoring
- Consider read replicas for read-heavy workloads

### Caching Strategy
- Redis cluster for session storage
- CloudFront CDN for static assets (optional)
- Application-level caching

## Contributing

When modifying infrastructure:

1. Test changes in development environment first
2. Update configuration files appropriately
3. Document any new resources or changes
4. Follow AWS best practices for security and cost optimization

## Support

For issues and questions:

1. Check the [Pulumi AWS documentation](https://www.pulumi.com/docs/clouds/aws/)
2. Review [AWS documentation](https://docs.aws.amazon.com/)
3. Check existing GitHub issues
4. Create a new issue with detailed information

## License

This infrastructure code is part of the RiffScribe project and follows the same license terms.