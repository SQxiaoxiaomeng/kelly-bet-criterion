SHELL := /bin/sh

COMPOSE := docker compose
PNPM := corepack pnpm

.DEFAULT_GOAL := help

.PHONY: help init up down restart logs ps migrate test test-backend test-frontend lint lint-backend lint-frontend build build-frontend

help: ## 显示可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

init: ## 创建本地 .env 配置文件（若不存在）
	@test -f .env || cp .env.example .env
	@echo "已确认 .env 文件存在。"

up: init ## 一键启动 PostgreSQL、Redis、后端、Worker 与前端
	$(COMPOSE) up --build -d
	$(COMPOSE) exec api alembic upgrade head
	@echo "前端：http://localhost:5173"
	@echo "后端：http://localhost:8000/api/v1/health"
	@echo "API 文档：http://localhost:8000/docs"

down: ## 停止全部本地服务
	$(COMPOSE) down

restart: down up ## 重启全部本地服务

logs: ## 跟踪全部服务日志
	$(COMPOSE) logs -f

ps: ## 查看服务状态
	$(COMPOSE) ps

migrate: ## 执行数据库迁移
	$(COMPOSE) exec api alembic upgrade head

test: test-backend test-frontend ## 运行所有测试、静态检查和前端构建

test-backend: ## 运行后端测试、Ruff 与 Mypy
	cd backend && python -m pytest -q && ruff check app tests && mypy app

test-frontend: ## 运行前端构建与 ESLint
	$(PNPM) --filter a-share-quant-lab-frontend run build
	$(PNPM) --filter a-share-quant-lab-frontend run lint

lint: lint-backend lint-frontend ## 运行全部静态检查

lint-backend: ## 运行后端 Ruff 与 Mypy
	cd backend && ruff check app tests && mypy app

lint-frontend: ## 运行前端 ESLint
	$(PNPM) --filter a-share-quant-lab-frontend run lint

build: build-frontend ## 构建前端生产包

build-frontend: ## 构建前端生产包
	$(PNPM) --filter a-share-quant-lab-frontend run build
