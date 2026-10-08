# DataMiner

DataMiner is a full-stack data collection and automation platform built with Python, Selenium, FastAPI, SQLAlchemy, SQLite, React and Vite.

## Overview

DataMiner combines automated web-data collection, a FastAPI backend, database persistence, job management, export workflows, logging and a React/Vite frontend into one application.

## Key Capabilities

- Automated web data collection
- Modular adapters and parsers
- FastAPI backend
- SQLAlchemy + SQLite persistence
- Job lifecycle management
- Authentication and protected application routes
- CSV/XLSX export workflows
- Logging and audit support
- Presets and reusable configurations
- React + Vite frontend
- Automated tests

## Technology Stack

**Backend:** Python, FastAPI, SQLAlchemy, SQLite  
**Automation:** Selenium  
**Frontend:** React, Vite  
**Data Export:** CSV, XLSX  
**Tooling:** Git, GitHub

## Repository Structure

```text
backend/       API, models, services and security
frontend/      React/Vite application
adapters/      Source-specific collection adapters
parsers/       Data parsing components