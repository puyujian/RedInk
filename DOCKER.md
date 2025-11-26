# RedInk Docker 部署文档

## 📋 目录

- [技术栈说明](#技术栈说明)
- [前置要求](#前置要求)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [服务管理](#服务管理)
- [健康检查](#健康检查)
- [故障排查](#故障排查)
- [生产部署](#生产部署)

## 🏗️ 技术栈说明

### 后端
- **语言**: Python 3.11+
- **框架**: Flask
- **ORM**: SQLAlchemy
- **任务队列**: Redis + RQ
- **包管理**: uv

### 前端
- **框架**: Vue 3 + TypeScript
- **构建工具**: Vite
- **状态管理**: Pinia
- **包管理**: pnpm
- **Web服务器**: Nginx (生产环境)

### 数据存储
- **数据库**: SQLite（默认）/ MySQL 8.0（可选）
- **缓存/队列**: Redis 7

## 📦 前置要求

- Docker Engine 20.10+
- Docker Compose 2.0+
- 2GB+ 可用内存（SQLite 模式）
- 4GB+ 可用内存（MySQL 模式）
- 5GB+ 可用磁盘空间

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/HisMax/RedInk.git
cd RedInk
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.docker .env

# 编辑 .env 文件，填入你的 API Keys
vim .env
```

**必填配置项**:
```env
GOOGLE_CLOUD_API_KEY=your_google_cloud_api_key_here
IMAGE_API_KEY=your_image_api_key_here
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
```

### 3. 配置图片生成服务

```bash
# 复制图片服务配置模板
cp image_providers.yaml.example image_providers.yaml

# 编辑配置文件
vim image_providers.yaml
```

### 4. 启动所有服务

```bash
# 一键启动所有服务（后台运行）
docker compose up -d

# 查看启动日志
docker compose logs -f
```

### 5. 访问应用

- **前端**: http://localhost
- **后端 API**: http://localhost:12398
- **API 文档**: http://localhost:12398/

### 6. 数据库说明

**默认配置（推荐新手）：**
- 使用 **SQLite**，无需配置，数据保存在 `./data/redink.db`
- 服务启动时自动初始化数据库
- 适合开发、测试和中小型部署

**使用 MySQL（可选）：**
```bash
# 1. 编辑 .env 文件，启用 MySQL 配置
MYSQL_ROOT_PASSWORD=your_strong_password
MYSQL_DATABASE=redink
MYSQL_USER=redink
MYSQL_PASSWORD=your_mysql_password
DATABASE_URL=mysql+pymysql://redink:your_mysql_password@mysql:3306/redink

# 2. 启动时附加 mysql profile
docker compose --profile mysql up -d

# 3. 数据库会自动初始化
```

**手动初始化数据库（如需要）：**
```bash
docker compose exec backend python -m backend.init_db
```

## ⚙️ 配置说明

### 服务端口映射

| 服务 | 容器端口 | 主机端口 | 说明 |
|------|---------|---------|------|
| frontend | 80 | 80 | 前端 Web 界面 |
| backend | 12398 | 12398 | 后端 API 服务 |
| redis | 6379 | 6379 | Redis 缓存和队列 |
| mysql（可选） | 3306 | 3306 | MySQL 数据库（启用 `--profile mysql` 时生效） |

### 数据持久化

所有重要数据都通过 Docker volumes / 目录 持久化存储：

- `./data`: SQLite 数据库文件（默认）
- `mysql-data`: MySQL 数据库文件（启用时）
- `redis-data`: Redis 持久化数据
- `./output`: 生成的图片文件
- `./history`: 用户历史记录

### 环境变量详解

```env
# API 配置（必填）
GOOGLE_CLOUD_API_KEY=         # Gemini API Key
IMAGE_API_KEY=                # 图片生成 API Key
TEXT_API_KEY=                 # 自定义文字生成 API Key（可选）

# 数据库配置（默认使用 SQLite，无需配置）
DATABASE_URL=                 # 数据库连接 URL
                              # SQLite（默认）: sqlite:////app/data/redink.db
                              # MySQL 示例: mysql+pymysql://user:pass@mysql:3306/redink

# MySQL 配置（仅在使用 MySQL 时需要）
MYSQL_ROOT_PASSWORD=          # MySQL root 密码
MYSQL_DATABASE=redink         # 数据库名称
MYSQL_USER=redink             # 数据库用户
MYSQL_PASSWORD=               # 数据库密码

# JWT 配置（必填）
JWT_SECRET_KEY=               # JWT 密钥（生产环境必须修改为强随机字符串）
JWT_ACCESS_EXPIRES=900        # Access Token 有效期（秒）
JWT_REFRESH_EXPIRES=604800    # Refresh Token 有效期（秒）

# Flask 配置
FLASK_DEBUG=False             # 调试模式（生产环境设为 False）
```

## 🔧 服务管理

### 启动服务

```bash
# 启动所有服务
docker compose up -d

# 启动指定服务
docker compose up -d backend frontend

# 查看服务状态
docker compose ps
```

### 停止服务

```bash
# 停止所有服务
docker compose down

# 停止并删除数据卷（危险操作！）
docker compose down -v
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启指定服务
docker compose restart backend
```

### 查看日志

```bash
# 查看所有服务日志
docker compose logs -f

# 查看指定服务日志
docker compose logs -f backend

# 查看最近 100 行日志
docker compose logs --tail=100 backend
```

### 进入容器

```bash
# 进入后端容器
docker compose exec backend sh

# 进入数据库容器
docker compose exec mysql mysql -u redink -p

# 进入 Redis 容器
docker compose exec redis redis-cli
```

## 🏥 健康检查

### 自动健康检查

所有服务都配置了健康检查，可以查看服务健康状态：

```bash
docker compose ps
```

### 手动健康检查

**后端 API**:
```bash
curl http://localhost:12398/
```

**前端**:
```bash
curl http://localhost/
```

**Redis**:
```bash
docker compose exec redis redis-cli ping
# 应返回: PONG
```

**MySQL**:
```bash
docker compose exec mysql mysqladmin ping -h localhost -u root -p
# 应返回: mysqld is alive
```

## 🔍 故障排查

### 1. 服务无法启动

```bash
# 查看详细日志
docker compose logs backend
docker compose logs worker

# 检查配置文件
cat .env
cat image_providers.yaml
```

### 2. 数据库连接失败

```bash
# 检查 MySQL 服务状态
docker compose ps mysql

# 检查数据库日志
docker compose logs mysql

# 手动测试连接
docker compose exec mysql mysql -u redink -p
```

### 3. Redis 连接失败

```bash
# 检查 Redis 服务状态
docker compose ps redis

# 测试连接
docker compose exec redis redis-cli ping
```

### 4. Worker 任务不执行

```bash
# 查看 Worker 日志
docker compose logs -f worker

# 检查 Redis 队列
docker compose exec redis redis-cli
> KEYS *queue*
> LLEN outline_queue
> LLEN image_queue
```

### 5. 前端无法访问后端

检查 Nginx 配置和网络：

```bash
# 查看前端日志
docker compose logs frontend

# 检查网络连接
docker compose exec frontend ping backend
```

### 6. 重建服务

如果服务出现问题，可以尝试重建：

```bash
# 停止并删除容器
docker compose down

# 重新构建镜像
docker compose build --no-cache

# 启动服务
docker compose up -d
```

## 🚀 生产部署

### 1. 安全配置

**修改所有默认密码**:

```env
# .env 文件
JWT_SECRET_KEY=<使用强随机字符串>
MYSQL_ROOT_PASSWORD=<使用强密码>
MYSQL_PASSWORD=<使用强密码>
```

**生成安全密钥**:
```bash
# 生成 JWT 密钥
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 2. 禁用调试模式

```env
FLASK_DEBUG=False
```

### 3. 配置 HTTPS

使用 Nginx 反向代理和 Let's Encrypt SSL 证书：

```nginx
# nginx-proxy.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4. 配置备份

定期备份数据库和生成的文件：

```bash
# 备份脚本示例
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)

# 备份数据库
docker compose exec mysql mysqldump -u redink -p redink > backup_${DATE}.sql

# 备份生成的文件
tar -czf output_${DATE}.tar.gz output/ history/
```

### 5. 监控和日志

配置日志轮转和监控：

```yaml
# docker compose.yaml 中添加日志配置
services:
  backend:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 6. 性能优化

**增加 Worker 数量**:

```yaml
# docker compose.yaml
services:
  worker:
    deploy:
      replicas: 3  # 运行 3 个 worker 实例
```

**调整数据库配置**:

```yaml
services:
  mysql:
    command: >
      --max_connections=200
      --innodb_buffer_pool_size=1G
      --query_cache_size=64M
```

## 📊 GitHub Container Registry

### 使用预构建镜像

如果项目已经发布到 GitHub Container Registry，可以直接使用：

```yaml
# docker compose.production.yaml
services:
  backend:
    image: ghcr.io/hismax/redink/backend:latest
    # ... 其他配置

  frontend:
    image: ghcr.io/hismax/redink/frontend:latest
    # ... 其他配置
```

### 拉取镜像

```bash
# 登录 GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# 拉取最新镜像
docker pull ghcr.io/hismax/redink/backend:latest
docker pull ghcr.io/hismax/redink/frontend:latest
```

## 🤝 CI/CD 工作流

项目配置了 GitHub Actions 自动构建工作流：

- **触发条件**: 推送到 `main` 分支
- **构建内容**: 
  - 后端 Docker 镜像
  - 前端 Docker 镜像
- **镜像标签**:
  - `latest`: 最新版本
  - `sha-<commit>`: 特定提交版本

查看工作流文件: `.github/workflows/docker-build.yml`

## 📝 常见命令速查

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 查看日志
docker compose logs -f backend

# 重启服务
docker compose restart backend

# 进入容器
docker compose exec backend sh

# 查看状态
docker compose ps

# 重建镜像
docker compose build --no-cache

# 清理所有内容（危险！）
docker compose down -v --rmi all
```

## 🆘 获取帮助

如遇到问题，请：

1. 查看 [故障排查](#故障排查) 章节
2. 查看服务日志：`docker compose logs -f`
3. 提交 Issue: https://github.com/HisMax/RedInk/issues
4. 联系作者：histonemax@gmail.com

## 📄 相关文档

- [项目主文档](README.md)
- [API 文档](http://localhost:12398/)
- [Docker 官方文档](https://docs.docker.com/)
- [Docker Compose 文档](https://docs.docker.com/compose/)

---

**祝您使用愉快！** 🎉
