# Docker Compose Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Docker Compose deployment for database, API, and Web services with Base + Override pattern for dev/prod environments.

**Architecture:** Three-service setup (db, api, web) using docker-compose.yml as base configuration, with docker-compose.dev.yml and docker-compose.prod.yml for environment-specific overrides. Development uses Vite dev server with hot reload; production uses nginx for static hosting and reverse proxy.

**Tech Stack:** Docker Compose, PostgreSQL + pgvector, FastAPI, React + Vite, nginx

---

## Task 1: Update Base docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Read current docker-compose.yml**

Run: `cat docker-compose.yml`
Expected: See existing db service configuration

**Step 2: Update docker-compose.yml to add api and web services**

Replace the entire file with:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: bridge_rag_db
    environment:
      POSTGRES_DB: bridge_rag
      POSTGRES_USER: bridge
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-bridge}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - bridge_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bridge -d bridge_rag"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: bridge_rag_api
    environment:
      DATABASE_URL: postgresql+psycopg://bridge:${POSTGRES_PASSWORD:-bridge}@db:5432/bridge_rag
      ZHIPU_API_KEY: ${ZHIPU_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - bridge_net

  web:
    container_name: bridge_rag_web
    depends_on:
      - api
    networks:
      - bridge_net

volumes:
  pgdata:

networks:
  bridge_net:
    driver: bridge
```

**Step 3: Verify syntax**

Run: `docker compose -f docker-compose.yml config`
Expected: Valid YAML output with no errors

**Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add api and web services to base docker-compose

Add base configuration for three services:
- db: PostgreSQL with pgvector (existing, updated with network)
- api: FastAPI service built from Dockerfile
- web: Base configuration (build/ports in override files)

Use environment variables for DATABASE_URL and ZHIPU_API_KEY.
Add bridge_net network for inter-service communication.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create docker-compose.dev.yml

**Files:**
- Create: `docker-compose.dev.yml`

**Step 1: Create docker-compose.dev.yml**

```yaml
services:
  db:
    ports:
      - "5433:5432"  # Expose database for GUI tools

  api:
    ports:
      - "8000:8000"  # Expose API for direct testing
    volumes:
      - ./app:/app/app              # Mount source code
      - ./config:/app/config
      - ./data:/app/data
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build:
      context: ./web
      dockerfile: Dockerfile.dev
    ports:
      - "3000:5173"   # Vite dev server port mapping
    volumes:
      - ./web/src:/app/src          # Mount source for hot reload
      - ./web/public:/app/public
      - /app/node_modules           # Prevent overwriting container node_modules
    environment:
      - VITE_API_URL=http://localhost:8000
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.yml -f docker-compose.dev.yml config`
Expected: Valid merged YAML with all dev overrides applied

**Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat: add development environment override

Development features:
- Expose all ports (db:5433, api:8000, web:3000)
- Mount source code for hot reload
- API uses --reload flag
- Web uses Vite dev server

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create docker-compose.prod.yml

**Files:**
- Create: `docker-compose.prod.yml`

**Step 1: Create docker-compose.prod.yml**

```yaml
services:
  db:
    restart: always
    # No port exposure - container-only access

  api:
    restart: always
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    # No port exposure - accessed only via nginx

  web:
    build:
      context: ./web
      dockerfile: Dockerfile.prod
      args:
        VITE_API_URL: /api  # Production API accessed via nginx proxy
    ports:
      - "80:80"
    restart: always
```

**Step 2: Verify syntax**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
Expected: Valid merged YAML with production overrides

**Step 3: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat: add production environment override

Production features:
- Only expose port 80 (nginx)
- No source code mounts (use build artifacts)
- API uses 4 workers for performance
- All services have restart: always
- VITE_API_URL set to /api for nginx proxy

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create web/Dockerfile.dev

**Files:**
- Create: `web/Dockerfile.dev`

**Step 1: Create web/Dockerfile.dev**

```dockerfile
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

**Step 2: Verify Dockerfile syntax**

Run: `docker build -f web/Dockerfile.dev -t test-web-dev web/ --no-cache 2>&1 | head -20`
Expected: Build starts successfully (may fail on missing files, that's ok for now)

**Step 3: Commit**

```bash
git add web/Dockerfile.dev
git commit -m "feat: add web development Dockerfile

Uses node:20-alpine and runs Vite dev server on 0.0.0.0:5173.
Supports hot reload when source is mounted via volume.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Create web/Dockerfile.prod

**Files:**
- Create: `web/Dockerfile.prod`

**Step 1: Create web/Dockerfile.prod**

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**Step 2: Verify Dockerfile syntax**

Run: `docker build -f web/Dockerfile.prod -t test-web-prod web/ --no-cache 2>&1 | head -20`
Expected: Build starts (may fail on missing nginx.conf, that's ok)

**Step 3: Commit**

```bash
git add web/Dockerfile.prod
git commit -m "feat: add web production Dockerfile with multi-stage build

Stage 1: Build React app with Vite
Stage 2: Serve with nginx from alpine image

Accepts VITE_API_URL build arg for API endpoint configuration.
Final image only contains nginx + static assets.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Create nginx configuration

**Files:**
- Create: `nginx/nginx.conf`

**Step 1: Create nginx directory and config file**

```bash
mkdir -p nginx
```

Create `nginx/nginx.conf`:

```nginx
server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Frontend static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API reverse proxy
    location /api {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
}
```

**Step 2: Verify nginx config syntax**

Run: `docker run --rm -v $(pwd)/nginx/nginx.conf:/etc/nginx/conf.d/default.conf nginx:alpine nginx -t`
Expected: "nginx: configuration file /etc/nginx/nginx.conf test is successful"

**Step 3: Commit**

```bash
git add nginx/nginx.conf
git commit -m "feat: add nginx configuration for production

Features:
- Serve React static files from /usr/share/nginx/html
- Reverse proxy /api requests to api:8000
- SPA support with try_files fallback to index.html
- Gzip compression for text/json/js files

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update app/main.py with CORS

**Files:**
- Modify: `app/main.py`

**Step 1: Read current app/main.py**

Run: `head -30 app/main.py`
Expected: See FastAPI app initialization

**Step 2: Add CORS middleware after app initialization**

Find this section (around line 10-15):
```python
app = FastAPI(title="Bridge RAG API", version="1.0.0")
```

Add after it:
```python
# CORS middleware for local development
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Step 3: Verify syntax**

Run: `python -m py_compile app/main.py`
Expected: No output (successful compilation)

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: add CORS middleware for web development

Allow requests from Vite dev server (3000, 5173) for local development.
Production requests come from same origin via nginx, no CORS needed.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Makefile

**Files:**
- Create: `Makefile`

**Step 1: Create Makefile**

```makefile
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
```

**Step 2: Verify Makefile syntax**

Run: `make -n dev`
Expected: Shows the command that would be executed

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat: add Makefile for simplified Docker commands

Provides shortcuts:
- make dev: start development environment
- make prod: start production environment
- make stop: stop services
- make clean: stop and remove volumes
- make logs: view logs
- make build: rebuild images
- make test: run pytest

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update .gitignore

**Files:**
- Modify: `.gitignore`

**Step 1: Read current .gitignore**

Run: `cat .gitignore`
Expected: See existing ignore patterns

**Step 2: Add Docker-related ignores**

Append to `.gitignore`:

```
# Docker
.env
nginx/logs/
```

**Step 3: Verify .gitignore**

Run: `git check-ignore -v .env`
Expected: Shows that .env is ignored

**Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: add Docker-related patterns to .gitignore

Ignore .env file (contains sensitive keys) and nginx logs directory.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update web/vite.config.ts proxy

**Files:**
- Modify: `web/vite.config.ts`

**Step 1: Read current vite.config.ts**

Run: `cat web/vite.config.ts`
Expected: See existing Vite configuration

**Step 2: Add proxy configuration**

Find the `defineConfig` section and ensure it has:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

**Step 3: Verify TypeScript syntax**

Run: `cd web && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to vite.config.ts

**Step 4: Commit**

```bash
git add web/vite.config.ts
git commit -m "feat: add Vite proxy for API requests

Proxy /api requests to localhost:8000 during development.
Allows frontend to use relative API paths in both dev and prod.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Integration Test - Development Environment

**Files:**
- N/A (testing only)

**Step 1: Set environment variables**

Run:
```bash
export ZHIPU_API_KEY="test_key_placeholder"
export POSTGRES_PASSWORD="bridge"
```

**Step 2: Start development environment**

Run: `make dev-build`
Expected: All three services build and start successfully

**Step 3: Verify services are running**

Run: `docker compose -f docker-compose.yml -f docker-compose.dev.yml ps`
Expected: All services show "running" or "healthy" status

**Step 4: Test database connection**

Run: `docker exec bridge_rag_db pg_isready -U bridge -d bridge_rag`
Expected: "accepting connections"

**Step 5: Test API health endpoint**

Run: `curl http://localhost:8000/health`
Expected: `{"status":"healthy"}`

**Step 6: Test web server**

Run: `curl -I http://localhost:3000`
Expected: HTTP 200 response

**Step 7: Stop services**

Run: `make stop`

**Step 8: Document test results**

No commit needed - verification only

---

## Task 12: Integration Test - Production Environment

**Files:**
- N/A (testing only)

**Step 1: Set environment variables**

Run:
```bash
export ZHIPU_API_KEY="test_key_placeholder"
export POSTGRES_PASSWORD="bridge"
```

**Step 2: Start production environment**

Run: `make prod-build`
Expected: All three services build and start in background

**Step 3: Verify services are running**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml ps`
Expected: All services show "running" or "healthy" status

**Step 4: Test nginx serves frontend**

Run: `curl -I http://localhost:80`
Expected: HTTP 200 response with nginx headers

**Step 5: Test API via nginx proxy**

Run: `curl http://localhost:80/api/health`
Expected: `{"status":"healthy"}`

**Step 6: Verify no direct API port exposure**

Run: `curl http://localhost:8000/health 2>&1 || echo "Port not exposed (expected)"`
Expected: Connection refused (port not exposed)

**Step 7: Stop services**

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`

**Step 8: Document test results**

No commit needed - verification only

---

## Task 13: Create deployment documentation commit

**Files:**
- N/A (summary commit only)

**Step 1: Verify all files are committed**

Run: `git status`
Expected: "nothing to commit, working tree clean"

**Step 2: Review commit history**

Run: `git log --oneline | head -15`
Expected: See all 12 implementation commits

**Step 3: Push to remote**

Run: `git push -u origin feature/docker-deployment`
Expected: Branch pushed successfully

---

## Summary

This plan implements Docker Compose deployment with:

1. **Base configuration** (docker-compose.yml) - shared service definitions
2. **Dev override** (docker-compose.dev.yml) - hot reload, all ports exposed
3. **Prod override** (docker-compose.prod.yml) - nginx, single port, optimized
4. **Dockerfiles** - separate dev/prod for web service
5. **nginx config** - reverse proxy and static hosting
6. **CORS** - API middleware for local development
7. **Makefile** - simplified commands
8. **Integration tests** - verify both environments work

**Total commits:** 12 (11 implementation + docs already committed)
**Estimated time:** 45-60 minutes
**Testing:** Manual integration testing for dev and prod environments

**Key principles applied:**
- DRY: Base + Override pattern avoids duplication
- YAGNI: Only dev and prod environments, no premature optimization
- TDD-adjacent: Integration tests verify each environment works
- Frequent commits: One logical change per commit
