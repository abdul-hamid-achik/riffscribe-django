# RiffScribe Makefile for common operations

.PHONY: help build up down logs shell migrate test clean

help: ## Show this help message
	@echo "RiffScribe Development Commands"
	@echo "==============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker containers
	docker-compose build

up: ## Start all services
	docker-compose up -d
	@echo "✅ Services started:"
	@echo "   Django: http://localhost:8000"
	@echo "   Flower: http://localhost:5555"

down: ## Stop all services
	docker-compose down

logs: ## Show logs
	docker-compose logs -f

shell: ## Open Django shell
	docker-compose exec django python manage.py shell

bash: ## Open bash in Django container
	docker-compose exec django bash

migrate: ## Run database migrations
	docker-compose exec django python manage.py migrate

makemigrations: ## Create new migrations
	docker-compose exec django python manage.py makemigrations

createsuperuser: ## Create Django superuser
	docker-compose exec django python manage.py createsuperuser

test: ## Run tests
	docker-compose exec django python manage.py test

test-pipeline: ## Test ML pipeline
	docker-compose exec django python scripts/test_pipeline.py

install-models: ## Download ML models
	docker-compose exec django python scripts/download_models.py

collect-static: ## Collect static files
	docker-compose exec django python manage.py collectstatic --noinput

clean: ## Clean up containers and volumes
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

reset-db: ## Reset database
	docker-compose down -v
	docker-compose up -d db redis
	sleep 5
	docker-compose exec django python manage.py migrate
	@echo "✅ Database reset complete"

dev-install: ## Install development dependencies locally
	pip install -r requirements.txt
	pip install -r requirements-ml.txt

dev-run: ## Run Django locally (requires Redis in Docker)
	docker-compose up -d redis db
	python manage.py runserver

celery-worker: ## Run Celery worker locally
	celery -A riffscribe worker -l info

celery-flower: ## Run Flower locally
	celery -A riffscribe flower

# Production commands
prod-build: ## Build for production
	docker-compose -f docker-compose.prod.yml build

prod-up: ## Start production services
	docker-compose -f docker-compose.prod.yml up -d

prod-logs: ## Show production logs
	docker-compose -f docker-compose.prod.yml logs -f