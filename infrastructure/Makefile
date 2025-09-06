# RiffScribe Infrastructure Makefile
# Simplified commands for AWS deployment using Pulumi

.PHONY: help install dev-deploy dev-preview dev-destroy staging-deploy staging-preview staging-destroy prod-deploy prod-preview prod-destroy clean

# Default target
help:
	@echo "RiffScribe Infrastructure Management"
	@echo ""
	@echo "Available targets:"
	@echo "  install       - Install Pulumi and dependencies"
	@echo "  dev-deploy    - Deploy development environment"
	@echo "  dev-preview   - Preview development changes"
	@echo "  dev-destroy   - Destroy development environment"
	@echo "  staging-deploy   - Deploy staging environment"
	@echo "  staging-preview  - Preview staging changes"
	@echo "  staging-destroy  - Destroy staging environment"
	@echo "  prod-deploy   - Deploy production environment"
	@echo "  prod-preview  - Preview production changes"
	@echo "  prod-destroy  - Destroy production environment"
	@echo "  clean         - Clean up local files"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - AWS CLI configured with credentials"
	@echo "  - Environment variables set (copy example.env to .env)"
	@echo "  - Container images built and pushed to registry"

# Install dependencies
install:
	@echo "Installing Pulumi and dependencies..."
	@which pulumi >/dev/null || (echo "Please install Pulumi CLI first: https://www.pulumi.com/docs/get-started/install/" && exit 1)
	@cd .. && uv sync --extra infrastructure

# Development environment targets
dev-deploy:
	@echo "Deploying development environment..."
	@python scripts/deploy.py deploy --environment dev

dev-preview:
	@echo "Previewing development environment changes..."
	@python scripts/deploy.py preview --environment dev

dev-destroy:
	@echo "Destroying development environment..."
	@python scripts/deploy.py destroy --environment dev

# Staging environment targets
staging-deploy:
	@echo "Deploying staging environment..."
	@python scripts/deploy.py deploy --environment staging

staging-preview:
	@echo "Previewing staging environment changes..."
	@python scripts/deploy.py preview --environment staging

staging-destroy:
	@echo "Destroying staging environment..."
	@python scripts/deploy.py destroy --environment staging

# Production environment targets
prod-deploy:
	@echo "Deploying production environment..."
	@echo "⚠️  WARNING: This will deploy to production!"
	@read -p "Are you sure? (y/N) " confirm && [ "$$confirm" = "y" ] || exit 1
	@python scripts/deploy.py deploy --environment prod

prod-preview:
	@echo "Previewing production environment changes..."
	@python scripts/deploy.py preview --environment prod

prod-destroy:
	@echo "Destroying production environment..."
	@echo "⚠️  WARNING: This will destroy production infrastructure!"
	@read -p "Are you sure? This cannot be undone! (y/N) " confirm && [ "$$confirm" = "y" ] || exit 1
	@python scripts/deploy.py destroy --environment prod

# Cleanup
clean:
	@echo "Cleaning up temporary files..."
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} +
