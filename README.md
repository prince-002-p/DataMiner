# DataMiner

Full-stack data collection and automation platform built with Python, Selenium, FastAPI, SQLAlchemy, SQLite, React and Vite.

## Overview

DataMiner combines automated web-data collection, a FastAPI backend, database persistence, job management, export workflows, logging and a React/Vite frontend.

## Key capabilities

- Automated web data collection
- Modular adapters and parsers
- FastAPI backend
- SQLAlchemy + SQLite persistence
- Job lifecycle management
- Authentication and protected routes
- CSV/XLSX export workflows
- Logging and audit support
- Presets and reusable configurations
- React + Vite frontend
- Automated tests

## Technology stack

**Backend:** Python, FastAPI, SQLAlchemy, SQLite  
**Automation:** Selenium  
**Frontend:** React, Vite  
**Export:** CSV, XLSX

## Structure

```text
backend/       API, models, services and security
frontend/      React/Vite application
adapters/      Source-specific collection adapters
parsers/       Data parsing components
tests/         Test suite
```

## Security

Do not commit real credentials, API keys, JWT secrets, generated exports, local databases or dependency directories. Configure secrets through environment variables before production use.

## Status

Active development.
