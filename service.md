# 策知 · CentOS Stream 9 服务器部署指南

本指南详细介绍如何在 CentOS Stream 9 服务器上从零部署「策知 — 行业资讯与政策智能分析平台」。

**系统架构概览：**

| 组件 | 技术栈 | 端口 | 说明 |
|------|--------|------|------|
| 后端 API | FastAPI + Uvicorn (Python 3.11+) | 8000 | 仅监听 127.0.0.1，由 Nginx 反代 |
| 前端 | Vue 3 + Vite (构建为静态文件) | 80/443 | 由 Nginx 托管 |
| 数据库 | SQLite (aiosqlite) | — | 文件型，无需独立服务 |
| 定时任务 | APScheduler (进程内) | — | 单 worker 运行 |
| 反向代理 | Nginx | 80/443 | 静态文件 + API 代理 |

> **重要提示：** 后端必须以 `--workers 1` 运行。APScheduler 在 FastAPI 进程内运行，多 worker 会导致重复调度。

---

## 一、服务器环境准备

### 1.1 系统初始配置

以 root 用户登录服务器后，首先确认系统版本：

```bash
cat /etc/redhat-release
# 预期输出: CentOS Stream release 9
```

### 1.2 更新系统并安装基础工具

```bash
# 更新所有已安装的包到最新版本
dnf update -y

# 安装基础开发工具和常用工具
dnf groupinstall -y "Development Tools"
dnf install -y wget curl vim git tar gzip unzip \
    epel-release \
    openssl-devel bzip2-devel libffi-devel \
    zlib-devel readline-devel sqlite-devel \
    xz-devel ncurses-devel
```

### 1.3 创建项目用户

出于安全考虑，不使用 root 运行应用服务，创建专用用户：

```bash
# 创建系统用户 aitext，指定家目录，不生成登录密码（通过 SSH 密钥登录）
useradd -m -s /bin/bash aitext

# 为 aitext 用户设置密码（部署时使用，建议设置为强密码）
passwd aitext

# 将 aitext 用户加入 wheel 组（需要 sudo 权限时使用）
usermod -aG wheel aitext
```

### 1.4 配置防火墙（开放 80 和 443 端口）

CentOS Stream 9 默认使用 firewalld：

```bash
# 确认 firewalld 已启动并设为开机自启
systemctl enable --now firewalld

# 开放 HTTP (80) 和 HTTPS (443) 端口
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https

# 开放 SSH（如果默认已开放可跳过）
firewall-cmd --permanent --add-service=ssh

# 重新加载防火墙使规则生效
firewall-cmd --reload

# 查看当前开放的端口和服务
firewall-cmd --list-all
```

> **注意：** 后端运行在 8000 端口，但仅监听 127.0.0.1，无需在防火墙中开放。外部流量通过 Nginx 的 80/443 端口转发。

---

## 二、安装 Python 环境

CentOS Stream 9 默认的 Python 版本为 3.9，本项目需要 Python 3.11+。推荐使用 dnf 直接安装 python3.11；如果需要更高版本，可从源码编译。

### 2.1 方式一：使用 dnf 安装 Python 3.11（推荐）

```bash
# 安装 Python 3.11 及 pip
dnf install -y python3.11 python3.11-pip python3.11-devel

# 验证版本
python3.11 --version
# 预期输出: Python 3.11.x

pip3.11 --version
```

### 2.2 方式二：从源码编译安装 Python 3.12（可选）

如果需要 Python 3.12 或更高版本：

```bash
# 下载 Python 3.12 源码
cd /usr/local/src
wget https://www.python.org/ftp/python/3.12.8/Python-3.12.8.tgz

# 解压
tar -xzf Python-3.12.8.tgz
cd Python-3.12.8

# 编译安装（--enable-optimizations 会使编译变慢但运行更快）
./configure --enable-optimizations --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib"
make -j$(nproc)
make altinstall

# 配置动态链接库
echo "/usr/local/lib" > /etc/ld.so.conf.d/python3.12.conf
ldconfig

# 验证
python3.12 --version
pip3.12 --version
```

### 2.3 配置 pip 国内镜像源（清华源）

为所有用户配置 pip 清华镜像源，加速包下载：

```bash
# 创建 pip 配置目录
mkdir -p /etc/pip

# 写入清华镜像源配置
cat > /etc/pip.conf << 'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
EOF

# 同时为 aitext 用户配置（切换到 aitext 用户后执行）
su - aitext
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf << 'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
EOF
exit
```

### 2.4 创建虚拟环境（在项目部署阶段完成）

虚拟环境将在第四章节「部署后端」中与项目代码一起创建，此处仅确认 Python 版本可用即可。

---

## 三、安装 Node.js 环境

前端构建需要 Node.js 18+。推荐使用 NodeSource 官方仓库安装。

### 3.1 安装 Node.js 20 LTS（通过 NodeSource 仓库）

```bash
# 添加 NodeSource 仓库（Node.js 20 LTS）
curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -

# 安装 Node.js
dnf install -y nodejs

# 验证版本
node --version
# 预期输出: v20.x.x

npm --version
# 预期输出: 10.x.x
```

### 3.2 配置 npm 国内镜像

```bash
# 设置 npm 淘宝镜像源
npm config set registry https://registry.npmmirror.com

# 验证配置
npm config get registry
# 预期输出: https://registry.npmmirror.com
```

### 3.3 安装 pnpm（可选）

pnpm 比 npm 更快、磁盘占用更小，但使用 npm 也可以：

```bash
# 安装 pnpm（使用淘宝镜像）
npm install -g pnpm --registry=https://registry.npmmirror.com

# 配置 pnpm 镜像源
pnpm config set registry https://registry.npmmirror.com

# 验证
pnpm --version
```

> 下文前端构建命令以 `npm` 为例。如果使用 pnpm，将 `npm install` 替换为 `pnpm install`，`npm run build` 替换为 `pnpm build`。

---

## 四、部署后端

### 4.1 上传项目代码

以下提供两种方式将项目代码部署到服务器。

#### 方式一：使用 Git 克隆（推荐）

如果项目已推送到 Git 仓库：

```bash
# 切换到 aitext 用户
su - aitext

# 克隆项目到 /opt/aitext
sudo mkdir -p /opt/aitext
sudo chown aitext:aitext /opt/aitext
cd /opt/aitext
git clone https://your-repo-url/aitext-analysis-system.git .
```

#### 方式二：使用 scp 上传

在本地机器上执行：

```bash
# 在本地项目根目录执行，将项目打包上传到服务器
# Windows PowerShell（本地）
scp -r D:\text\PythonProjects\Play_projects\AIText-analysis-system aitext@your-server-ip:/tmp/aitext-upload

# 服务器端移动到目标目录
sudo mv /tmp/aitext-upload /opt/aitext
sudo chown -R aitext:aitext /opt/aitext
```

上传完成后，确认项目目录结构：

```bash
ls -la /opt/aitext/
# 应看到: backend/  frontend/  data/  README.md
```

### 4.2 创建并激活虚拟环境

```bash
# 确保以 aitext 用户操作
su - aitext
cd /opt/aitext/backend

# 使用 python3.11 创建虚拟环境
python3.11 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 验证 Python 版本
python --version
# 预期输出: Python 3.11.x
```

### 4.3 安装 Python 依赖

```bash
# 确保虚拟环境已激活（提示符前有 (.venv)）
cd /opt/aitext/backend
pip install -r requirements.txt
```

如果遇到 `lxml` 编译失败的错误，先安装系统依赖：

```bash
# 退出虚拟环境，安装 lxml 编译依赖
deactivate
sudo dnf install -y libxml2-devel libxslt-devel
# 重新激活虚拟环境并安装
source .venv/bin/activate
pip install -r requirements.txt
```

### 4.4 配置 config.py

编辑后端配置文件，根据生产环境修改关键参数：

```bash
cd /opt/aitext/backend
vim config.py
```

需要修改的关键配置项：

```python
# CORS — 添加你的生产域名（如果前后端同域，可保留默认，但建议加上域名）
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://your-domain.com",       # 新增：你的 HTTP 域名
    "https://your-domain.com",      # 新增：你的 HTTPS 域名
    "http://your-server-ip",        # 新增：服务器 IP（无域名时使用）
]

# SMTP 邮件配置 — 修改为你自己的 SMTP 信息
SMTP_CONFIG = {
    "enabled": True,
    "host": "smtp.qq.com",          # 你的 SMTP 服务器
    "port": 465,                    # SSL: 465, TLS: 587
    "use_ssl": True,
    "username": "your_email@qq.com",    # 你的发件邮箱
    "password": "your-smtp-authorization-code",  # SMTP 授权码（不是邮箱登录密码）
    "sender_name": "策知系统",
}
```

> **安全提示：** `config.py` 中包含 SMTP 密码等敏感信息，请确保该文件权限仅限 aitext 用户可读：
> ```bash
> chmod 600 /opt/aitext/backend/config.py
> ```

### 4.5 初始化数据库

数据库会在后端首次启动时自动创建和迁移。首次启动会：
- 创建 `data/ai_text.db` SQLite 数据库文件
- 创建所有数据表
- 创建默认管理员账号（用户名: `admin`，密码: `zhou1999`）
- 写入预置数据源（中国政府网、国家数据局等）

确保数据目录有正确权限：

```bash
# 创建数据目录（如果不存在）
mkdir -p /opt/aitext/data/pdfs
mkdir -p /opt/aitext/data/uploads

# 设置权限
chmod -R 755 /opt/aitext/data/
```

### 4.6 测试运行后端

```bash
# 确保虚拟环境已激活
cd /opt/aitext/backend
source .venv/bin/activate

# 手动启动测试（临时）
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

看到以下输出说明启动成功：

```
[App] 系统已启动 → http://localhost:8000/docs
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

在另一个终端验证 API 可用：

```bash
curl http://127.0.0.1:8000/
# 预期返回: {"message":"策知 · 行业资讯与政策智能分析平台 API","docs":"/docs"}

curl http://127.0.0.1:8000/docs
# 应返回 Swagger UI HTML 页面
```

确认无误后，按 `Ctrl + C` 停止测试进程，后续使用 systemd 管理服务。

### 4.7 配置 systemd 服务（详见第七章）

systemd 服务的详细配置请参考第七章「配置系统服务」。此处确认虚拟环境路径和启动命令：

```bash
# 确认虚拟环境中的 uvicorn 路径
ls /opt/aitext/backend/.venv/bin/uvicorn
# 应存在该文件
```

---

## 五、构建前端

### 5.1 安装前端依赖

```bash
# 以 aitext 用户操作
su - aitext
cd /opt/aitext/frontend

# 安装依赖
npm install
```

如果安装缓慢，确认已配置淘宝镜像（见第三章 3.2 节）。

### 5.2 配置 API 代理

前端通过 `axios` 的 `baseURL: '/api'` 发送请求。开发环境通过 Vite proxy 转发，**生产环境通过 Nginx 反代**，因此前端构建时无需额外配置 API 地址。

确认 `vite.config.js` 中的代理配置（仅开发环境使用，构建后不生效）：

```javascript
// vite.config.js — 开发环境配置，生产环境由 Nginx 处理
server: {
    port: 5173,
    proxy: {
        '/api': {
            target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
            changeOrigin: true,
        },
    },
},
```

> 生产环境中，前端和 API 由同一个 Nginx 服务提供（同源），`/api/` 请求会被 Nginx 反代到后端 8000 端口，无需修改前端代码。

### 5.3 构建前端

```bash
cd /opt/aitext/frontend

# 执行构建
npm run build
```

构建完成后，确认 `dist/` 目录已生成：

```bash
ls -la dist/
# 应看到: index.html  assets/
```

### 5.4 将 dist 目录部署到 Nginx

Nginx 默认的 Web 根目录通常为 `/usr/share/nginx/html`。可以选择以下两种方式之一：

#### 方式一：直接修改 Nginx 指向 dist 目录（推荐）

保持 dist 目录在项目内，Nginx 配置直接指向 `/opt/aitext/frontend/dist`。详见第六章 Nginx 配置。

#### 方式二：复制 dist 到 Nginx 默认目录

```bash
# 将构建产物复制到 Nginx 目录
sudo rm -rf /usr/share/nginx/html/*
sudo cp -r /opt/aitext/frontend/dist/* /usr/share/nginx/html/
sudo chown -R nginx:nginx /usr/share/nginx/html/
```

---

## 六、安装和配置 Nginx

### 6.1 安装 Nginx

```bash
# 安装 Nginx
sudo dnf install -y nginx

# 启动 Nginx 并设为开机自启
sudo systemctl enable --now nginx

# 验证 Nginx 状态
sudo systemctl status nginx
```

### 6.2 配置反向代理

创建站点配置文件。Nginx 需要处理三类请求：
1. **前端静态文件**：Vue 单页应用，所有非文件请求回退到 `index.html`
2. **API 请求**：`/api/` 路径反代到后端 8000 端口
3. **上传文件**：`/uploads/` 路径反代到后端（用户头像等静态资源）

```bash
# 移除默认站点配置（可选）
sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak 2>/dev/null || true

# 创建策知站点配置
sudo vim /etc/nginx/conf.d/aitext.conf
```

写入以下配置（将 `your-domain.com` 替换为你的域名或 IP）：

```nginx
server {
    listen 80;
    server_name your-domain.com;     # 替换为你的域名或服务器 IP

    # 前端静态文件根目录
    root /opt/aitext/frontend/dist;
    index index.html;

    # 上传文件大小限制（根据需要调整）
    client_max_body_size 50m;

    # Vue 单页应用路由 — 所有前端路由回退到 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理 — 所有 /api/ 请求转发到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 支持（如果未来需要）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置（AI 分析可能耗时较长）
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    # 上传文件代理（用户头像、上传的文件）
    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # API 文档代理（可选 — 生产环境可关闭以避免暴露文档）
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # 禁止访问隐藏文件
    location ~ /\. {
        deny all;
    }
}
```

> **安全提示：** 生产环境建议移除 `/docs` 和 `/openapi.json` 的代理配置，避免 API 文档被外部访问。

测试 Nginx 配置语法并重新加载：

```bash
# 测试配置语法
sudo nginx -t

# 重新加载配置
sudo nginx -s reload
```

### 6.3 配置 SSL/HTTPS（可选，使用 Let's Encrypt）

如果有域名，强烈建议配置 HTTPS。

#### 安装 Certbot

```bash
# 安装 EPEL 仓库（如果前面未安装）
sudo dnf install -y epel-release

# 安装 certbot 和 Nginx 插件
sudo dnf install -y certbot python3-certbot-nginx
```

#### 申请并自动配置 SSL 证书

```bash
# 确保域名已解析到服务器 IP，且 80 端口可访问
# 自动申请证书并修改 Nginx 配置
sudo certbot --nginx -d your-domain.com

# 按提示输入邮箱、同意条款、选择是否重定向 HTTP 到 HTTPS
```

Certbot 会自动修改 Nginx 配置，添加 SSL 证书路径和 HTTP 到 HTTPS 的重定向。

#### 设置证书自动续期

```bash
# 测试自动续期（dry-run）
sudo certbot renew --dry-run

# certbot 安装后会自动创建 systemd timer 进行续期，确认已启用
sudo systemctl enable --now certbot.timer
```

#### 手动配置 HTTPS（如果需要）

如果手动配置，Nginx SSL 配置参考：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    # HTTP 重定向到 HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # 以下配置与 6.2 节 HTTP 配置相同
    root /opt/aitext/frontend/dist;
    index index.html;
    client_max_body_size 50m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6.4 启动 Nginx 并设置开机自启

```bash
# 确保已启动并设为开机自启
sudo systemctl enable --now nginx

# 重新加载配置（修改配置后执行）
sudo systemctl reload nginx

# 查看状态
sudo systemctl status nginx
```

---

## 七、配置系统服务

### 7.1 创建后端 systemd 服务文件

创建 systemd 服务文件来管理后端进程：

```bash
sudo vim /etc/systemd/system/aitext.service
```

写入以下内容：

```ini
[Unit]
Description=AIText Analysis Backend (FastAPI + Uvicorn)
After=network.target

[Service]
Type=simple
User=aitext
Group=aitext
WorkingDirectory=/opt/aitext/backend
Environment="PATH=/opt/aitext/backend/.venv/bin:/usr/bin:/bin"
EnvironmentFile=/opt/aitext/backend/.env
ExecStart=/opt/aitext/backend/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5

# 安全限制
NoNewPrivileges=true
PrivateTmp=true

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aitext

[Install]
WantedBy=multi-user.target
```

> **说明：**
> - `--host 127.0.0.1`：仅监听本地，由 Nginx 反代对外提供服务，更安全。
> - `--workers 1`：必须为单 worker，因为 APScheduler 在进程内运行，多 worker 会导致重复调度。
> - `EnvironmentFile`：如果需要环境变量，创建 `.env` 文件；如果不需要，可删除此行。
> - `Restart=always`：进程异常退出后自动重启。

如果不需要环境变量文件，先删除 `EnvironmentFile` 行，或创建空文件：

```bash
# 如果使用 EnvironmentFile，创建 .env 文件
touch /opt/aitext/backend/.env
chown aitext:aitext /opt/aitext/backend/.env
chmod 600 /opt/aitext/backend/.env
```

### 7.2 设置开机自启

```bash
# 重新加载 systemd 配置（创建或修改 service 文件后必须执行）
sudo systemctl daemon-reload

# 启动后端服务
sudo systemctl start aitext

# 设置开机自启
sudo systemctl enable aitext

# 查看服务状态
sudo systemctl status aitext
```

确认服务正常运行：

```bash
# 检查端口监听
ss -tlnp | grep 8000
# 预期输出: LISTEN  127.0.0.1:8000

# 测试 API
curl http://127.0.0.1:8000/
# 预期返回: {"message":"策知 · 行业资讯与政策智能分析平台 API","docs":"/docs"}
```

### 7.3 日志管理

systemd 服务日志通过 `journalctl` 管理：

```bash
# 查看后端实时日志（跟踪模式）
sudo journalctl -u aitext -f

# 查看最近 100 行日志
sudo journalctl -u aitext -n 100

# 查看今天的日志
sudo journalctl -u aitext --since today

# 查看指定时间段日志
sudo journalctl -u aitext --since "2025-01-01 00:00:00" --until "2025-01-02 00:00:00"

# 查看错误日志
sudo journalctl -u aitext -p err

# 查看服务启动日志
sudo journalctl -u aitext -b
```

#### 配置日志轮转（防止日志过大）

systemd journal 默认有大小限制。可修改配置：

```bash
sudo vim /etc/systemd/journald.conf
```

修改以下参数：

```ini
[Journal]
SystemMaxUse=500M
SystemKeepFree=1G
MaxFileSec=1month
```

重启 journald 使配置生效：

```bash
sudo systemctl restart systemd-journald
```

---

## 八、防火墙与安全

### 8.1 配置 firewalld

```bash
# 确认 firewalld 运行状态
sudo systemctl status firewalld

# 查看当前规则
sudo firewall-cmd --list-all

# 确认已开放的服务
sudo firewall-cmd --list-services
# 预期包含: ssh http https

# 如果未开放，执行以下命令
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

> **注意：** 不要在防火墙中开放 8000 端口。后端仅监听 127.0.0.1:8000，外部不可直接访问，所有流量通过 Nginx 转发。

### 8.2 配置 fail2ban 防暴力破解（可选但推荐）

```bash
# 安装 fail2ban
sudo dnf install -y fail2ban fail2ban-firewalld

# 创建本地配置（不要直接修改 jail.conf）
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo vim /etc/fail2ban/jail.local
```

修改 SSH 防护配置：

```ini
[DEFAULT]
bantime = 3600        # 封禁时长（秒），1小时
findtime = 600        # 检测时间窗口（秒），10分钟
maxretry = 5          # 最大重试次数
banaction = firewallcmd-rich-rules[actiontype=]
backend = systemd

[sshd]
enabled = true
port = ssh
```

启动并设置开机自启：

```bash
sudo systemctl enable --now fail2ban

# 查看状态
sudo fail2ban-client status

# 查看 SSH 防护状态
sudo fail2ban-client status sshd
```

### 8.3 SSH 安全配置

编辑 SSH 配置文件增强安全性：

```bash
sudo vim /etc/ssh/sshd_config
```

修改以下配置项：

```ini
# 禁止 root 直接登录
PermitRootLogin no

# 禁止密码登录（仅允许密钥登录，需先配置好密钥再启用）
PasswordAuthentication no

# 限制可登录用户（仅允许 aitext 用户）
AllowUsers aitext

# 修改默认端口（可选，如果修改记得在防火墙中开放新端口）
# Port 2222

# 空闲超时自动断开
ClientAliveInterval 300
ClientAliveCountMax 2

# 禁止 X11 转发
X11Forwarding no
```

> **重要：** 启用 `PasswordAuthentication no` 之前，请确保已配置好 SSH 密钥登录，否则将无法登录服务器！

配置 SSH 密钥登录（在本地机器执行）：

```bash
# 本地生成密钥对（如果已有可跳过）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 将公钥上传到服务器
ssh-copy-id aitext@your-server-ip

# 测试密钥登录成功后，再禁用密码登录
```

重启 SSH 服务使配置生效：

```bash
sudo systemctl restart sshd
```

### 8.4 SELinux 配置

CentOS Stream 9 默认启用 SELinux。如果 Nginx 无法访问项目目录，需要调整 SELinux 上下文：

```bash
# 查看 SELinux 状态
getenforce
# 预期输出: Enforcing

# 如果 Nginx 报 403 Forbidden，为项目目录设置正确的 SELinux 上下文
sudo semanage fcontext -a -t httpd_sys_content_t "/opt/aitext/frontend/dist(/.*)?"
sudo restorecon -Rv /opt/aitext/frontend/dist

# 如果 Nginx 需要反代到后端端口，允许 httpd 网络连接
sudo setsebool -P httpd_can_network_connect 1
```

如果 `semanage` 命令不存在，先安装：

```bash
sudo dnf install -y policycoreutils-python-utils
```

---

## 九、日常维护

### 9.1 常用命令速查

#### 服务管理

```bash
# 重启后端服务
sudo systemctl restart aitext

# 停止后端服务
sudo systemctl stop aitext

# 启动后端服务
sudo systemctl start aitext

# 查看后端状态
sudo systemctl status aitext

# 重启 Nginx
sudo systemctl restart nginx

# 重新加载 Nginx 配置（不中断服务）
sudo systemctl reload nginx
```

#### 日志查看

```bash
# 后端实时日志
sudo journalctl -u aitext -f

# 后端最近 200 行日志
sudo journalctl -u aitext -n 200

# Nginx 错误日志
sudo tail -f /var/log/nginx/error.log

# Nginx 访问日志
sudo tail -f /var/log/nginx/access.log

# 查看所有系统日志
sudo journalctl -f
```

### 9.2 更新代码后部署流程

当项目代码更新后，按以下流程重新部署：

#### 更新后端

```bash
# 1. 拉取最新代码
su - aitext
cd /opt/aitext
git pull origin main

# 2. 激活虚拟环境
cd /opt/aitext/backend
source .venv/bin/activate

# 3. 更新依赖（如果 requirements.txt 有变化）
pip install -r requirements.txt

# 4. 退出虚拟环境
deactivate
exit

# 5. 重启后端服务
sudo systemctl restart aitext

# 6. 确认服务正常
sudo systemctl status aitext
curl http://127.0.0.1:8000/
```

#### 更新前端

```bash
# 1. 拉取最新代码（如果上面已执行可跳过）
su - aitext
cd /opt/aitext
git pull origin main

# 2. 安装依赖（如果 package.json 有变化）
cd /opt/aitext/frontend
npm install

# 3. 重新构建
npm run build

# 4. 退出用户
exit

# 5. 重新加载 Nginx（刷新静态文件缓存）
sudo systemctl reload nginx
```

#### 一键部署脚本（可选）

可创建部署脚本简化操作：

```bash
sudo vim /opt/aitext/deploy.sh
```

```bash
#!/bin/bash
set -e

PROJECT_DIR="/opt/aitext"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV="$BACKEND_DIR/.venv"

echo "===== 1. 拉取最新代码 ====="
cd "$PROJECT_DIR"
sudo -u aitext git pull origin main

echo "===== 2. 更新后端依赖 ====="
sudo -u aitext "$VENV/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

echo "===== 3. 构建前端 ====="
cd "$FRONTEND_DIR"
sudo -u aitext npm install
sudo -u aitext npm run build

echo "===== 4. 重启后端服务 ====="
systemctl restart aitext

echo "===== 5. 重新加载 Nginx ====="
systemctl reload nginx

echo "===== 6. 检查服务状态 ====="
systemctl status aitext --no-pager
curl -s http://127.0.0.1:8000/ && echo ""

echo "===== 部署完成 ====="
```

```bash
sudo chmod +x /opt/aitext/deploy.sh
# 执行部署
sudo /opt/aitext/deploy.sh
```

### 9.3 数据库备份

SQLite 是文件型数据库，备份简单。建议定期备份整个 `data/` 目录。

#### 手动备份

```bash
# 创建备份目录
sudo mkdir -p /opt/aitext-backups

# 备份数据库和 PDF 文件
BACKUP_NAME="aitext-backup-$(date +%Y%m%d-%H%M%S)"
sudo tar -czf "/opt/aitext-backups/${BACKUP_NAME}.tar.gz" \
    -C /opt/aitext \
    data/

# 查看备份文件
ls -lh /opt/aitext-backups/
```

#### 使用 SQLite 在线备份（更安全）

使用 SQLite 的 `.backup` 命令可以在数据库运行时安全备份：

```bash
# 安装 sqlite3 工具
sudo dnf install -y sqlite

# 在线备份数据库（不会阻塞写入）
BACKUP_NAME="aitext-db-$(date +%Y%m%d-%H%M%S).db"
sudo -u aitext sqlite3 /opt/aitext/data/ai_text.db ".backup '/opt/aitext-backups/${BACKUP_NAME}'"
```

#### 自动定时备份

创建备份脚本并配置 cron 定时任务：

```bash
sudo vim /opt/aitext-backups/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/opt/aitext-backups"
DATE=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=7

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# SQLite 在线备份
sqlite3 /opt/aitext/data/ai_text.db ".backup '$BACKUP_DIR/aitext-db-$DATE.db'"

# 备份 PDF 文件（每周一次完整备份即可，此处每天备份）
tar -czf "$BACKUP_DIR/aitext-pdfs-$DATE.tar.gz" -C /opt/aitext data/pdfs/

# 删除超过 KEEP_DAYS 天的旧备份
find "$BACKUP_DIR" -name "aitext-db-*.db" -mtime +$KEEP_DAYS -delete
find "$BACKUP_DIR" -name "aitext-pdfs-*.tar.gz" -mtime +$KEEP_DAYS -delete

echo "[$(date)] 备份完成: aitext-db-$DATE.db"
```

```bash
sudo chmod +x /opt/aitext-backups/backup.sh

# 配置 cron 定时任务（每天凌晨 3 点执行）
sudo crontab -e
```

在 crontab 中添加：

```cron
0 3 * * * /opt/aitext-backups/backup.sh >> /var/log/aitext-backup.log 2>&1
```

### 9.4 常见问题排查

#### 问题 1：访问网站返回 502 Bad Gateway

**原因：** Nginx 无法连接到后端服务。

```bash
# 1. 检查后端服务是否运行
sudo systemctl status aitext

# 2. 如果未运行，查看错误日志
sudo journalctl -u aitext -n 50

# 3. 检查端口是否监听
ss -tlnp | grep 8000

# 4. 手动测试后端
curl http://127.0.0.1:8000/

# 5. 重启服务
sudo systemctl restart aitext
```

#### 问题 2：前端页面空白或 404

**原因：** 前端未正确构建或 Nginx 配置错误。

```bash
# 1. 确认 dist 目录存在且有内容
ls -la /opt/aitext/frontend/dist/

# 2. 检查 Nginx 配置中的 root 路径
sudo nginx -T | grep root

# 3. 测试 Nginx 配置语法
sudo nginx -t

# 4. 检查 SELinux 是否阻止访问
sudo tail -f /var/log/audit/audit.log | grep nginx
# 如果有 AVC denied，执行：
sudo setsebool -P httpd_can_network_connect 1
sudo restorecon -Rv /opt/aitext/frontend/dist

# 5. 重新加载 Nginx
sudo systemctl reload nginx
```

#### 问题 3：API 请求返回 CORS 错误

**原因：** `config.py` 中 CORS_ORIGINS 未包含访问域名。

```bash
# 编辑配置文件，添加你的域名
vim /opt/aitext/backend/config.py
# 在 CORS_ORIGINS 列表中添加 "https://your-domain.com"

# 重启后端
sudo systemctl restart aitext
```

> 如果前端和 API 通过同一个 Nginx 服务提供（同源），通常不会出现 CORS 问题。

#### 问题 4：邮件发送失败

**原因：** SMTP 配置错误或网络不通。

```bash
# 1. 测试 SMTP 服务器连通性
curl -v telnet://smtp.qq.com:465

# 2. 检查 config.py 中的 SMTP 配置
grep -A 6 "SMTP_CONFIG" /opt/aitext/backend/config.py

# 3. 查看后端日志中的错误信息
sudo journalctl -u aitext | grep -i "smtp\|mail\|email"
```

#### 问题 5：定时采集任务不执行

**原因：** 后端进程未运行或多 worker 导致调度冲突。

```bash
# 1. 确认后端服务运行中
sudo systemctl status aitext

# 2. 确认只有单 worker
ps aux | grep uvicorn
# 应只有 1 个 uvicorn 进程

# 3. 检查定时任务日志
sudo journalctl -u aitext | grep -i "scheduler\|crawl\|采集"
```

#### 问题 6：数据库锁定 (database is locked)

**原因：** SQLite 并发写入冲突，通常因为多个进程同时写入。

```bash
# 1. 确保只有单个后端进程
ps aux | grep uvicorn
# 如果有多个进程，检查是否启动了多个服务

# 2. 重启服务
sudo systemctl restart aitext
```

#### 问题 7：磁盘空间不足

```bash
# 检查磁盘使用情况
df -h

# 检查项目目录大小
du -sh /opt/aitext/data/*
du -sh /opt/aitext/frontend/dist/

# 清理旧的日志
sudo journalctl --vacuum-time=7d

# 清理旧备份
find /opt/aitext-backups -mtime +30 -delete
```

---

## 附录：部署检查清单

完成所有步骤后，按以下清单逐项确认：

| 检查项 | 命令 | 预期结果 |
|--------|------|----------|
| 系统已更新 | `dnf history` | 无待更新包 |
| aitext 用户存在 | `id aitext` | 用户存在 |
| 防火墙已配置 | `firewall-cmd --list-services` | 包含 ssh http https |
| Python 3.11 可用 | `python3.11 --version` | Python 3.11.x |
| Node.js 可用 | `node --version` | v20.x.x |
| 虚拟环境已创建 | `ls /opt/aitext/backend/.venv/bin/python` | 文件存在 |
| 依赖已安装 | `/opt/aitext/backend/.venv/bin/pip list` | 列出所有包 |
| config.py 已配置 | `cat /opt/aitext/backend/config.py` | SMTP/CORS 已修改 |
| 数据目录有权限 | `ls -la /opt/aitext/data/` | aitext 用户拥有 |
| 前端已构建 | `ls /opt/aitext/frontend/dist/index.html` | 文件存在 |
| Nginx 运行中 | `systemctl status nginx` | active (running) |
| Nginx 配置正确 | `nginx -t` | syntax is ok |
| 后端服务运行中 | `systemctl status aitext` | active (running) |
| 后端端口监听 | `ss -tlnp \| grep 8000` | LISTEN 127.0.0.1:8000 |
| API 可访问 | `curl http://127.0.0.1:8000/` | 返回 JSON |
| 网站可访问 | 浏览器访问 `http://your-domain.com` | 显示登录页 |
| HTTPS 可用（可选） | 浏览器访问 `https://your-domain.com` | 证书有效 |
| 备份计划已配置 | `crontab -l` | 包含备份任务 |
