.PHONY: dev prod stop logs clean build test

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-build:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-build:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

stop:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

clean:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v

logs:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f

build:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build

test:
	pytest tests/ -v
