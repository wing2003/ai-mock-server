# Mock API 风控策略管理系统

## 项目简介
AI API Mock 系统，支持全维度风控模拟、可视化管理与自动化测试报告。

## 快速开始

### 1. 环境准备
确保已安装 Python 3.9+ 和 MySQL 8.2。

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置数据库
在 MySQL 中创建数据库：
```sql
CREATE DATABASE mock_risk_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 修改配置
复制 `.env.example` 为 `.env` 并修改数据库连接信息。

### 5. 运行服务
```bash
python main.py
```

## 目录结构
- `app/`: 核心业务代码（管理端、风控引擎、策略模块）
- `server/`: 原有 OpenAI Mock 接口实现
- `templates/`: Jinja2 前端模板
- `static/`: 静态资源文件
- `tests/`: 测试脚本与数据

## 技术栈
- **后端**: FastAPI, SQLAlchemy (Async), Uvicorn
- **数据库**: MySQL 8.2, Asyncmy
- **前端**: Jinja2, HTMX, Tailwind CSS
- **限流**: Limits (工业级滑动窗口)
