# Savvy Deploy App

A tiny, dependency-free Node.js web application that is ready to deploy. It includes a polished static landing page, a `/healthz` endpoint, automated tests, Docker support, and a GitHub Actions workflow.

## Requirements

- Node.js 20 or newer
- Docker, if you want to build the container image

## Run locally

```bash
npm start
```

Open <http://localhost:3000>.

## Test

```bash
npm test
```

## Health check

```bash
curl http://localhost:3000/healthz
```

The endpoint returns JSON with an `ok` status and is suitable for uptime checks, container health checks, and load balancer probes.

## Deploy with Docker

```bash
docker build -t savvy-deploy-app .
docker run --rm -p 3000:3000 savvy-deploy-app
```

## Deploy with Docker Compose

```bash
docker compose up --build
```

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Interface the HTTP server binds to. |
| `PORT` | `3000` | Port the HTTP server listens on. |
