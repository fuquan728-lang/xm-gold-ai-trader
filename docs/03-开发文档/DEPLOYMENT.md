# 🚀 部署指南

> 生产环境部署和运维指南

## 部署架构

### 单机部署架构
```
┌─────────────────────────────────────────────────┐
│                生产服务器                        │
├─────────────────────────────────────────────────┤
│  MT5 AI交易系统 V3.0                           │
│                                                 │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Python服务 │  │  数据库    │  │  Web服务 │ │
│  │ 主进程     │◀─▶│ SQLite    │  │ 仪表盘   │ │
│  └────────────┘  └────────────┘  └──────────┘ │
│         │              │               │       │
│         ▼              ▼               ▼       │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Socket服务 │  │  缓存      │  │ 监控系统 │ │
│  │ (8080)     │  │  LRU       │  │          │ │
│  └────────────┘  └────────────┘  └──────────┘ │
│         │                                      │
│         ▼                                      │
│  ┌────────────┐                                │
│  │ WebSocket  │                                │
│  │ (8081)     │                                │
│  └────────────┘                                │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│                MT5客户端                         │
│  (可分布在多台机器)                             │
└─────────────────────────────────────────────────┘
```

### 高可用部署架构
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  负载均衡器     │────│  应用服务器1    │────│  数据库集群     │
│  (Nginx/Haproxy)│    │  Python服务     │    │  PostgreSQL     │
│                 │    │  Socket/WS      │    │  主从复制       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │                       │
         │                      │                       │
         ▼                      ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  应用服务器2    │    │  缓存集群       │    │  监控服务器     │
│  Python服务     │    │  Redis集群      │    │  Prometheus     │
│  Socket/WS      │    │  会话共享       │    │  Grafana        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 环境要求

### 硬件要求
| 组件 | 最低配置 | 推荐配置 | 生产配置 |
|------|----------|----------|----------|
| **CPU** | 双核2.0GHz | 四核3.0GHz | 八核3.5GHz+ |
| **内存** | 4GB | 8GB | 16GB+ |
| **存储** | 10GB SSD | 50GB SSD | 200GB NVMe |
| **网络** | 100Mbps | 1Gbps | 1Gbps+（低延迟） |

### 软件要求
| 软件 | 版本 | 说明 |
|------|------|------|
| **操作系统** | Windows 10/11, Ubuntu 20.04+, CentOS 8+ | 推荐使用Linux服务器 |
| **Python** | 3.8+ | 推荐3.9或3.10 |
| **MT5终端** | Build 4000+ | 客户端需要MT5 |
| **数据库** | SQLite 3.35+ (嵌入式) | 或 PostgreSQL 13+ (生产) |
| **Web服务器** | 可选: Nginx 1.18+ | 用于反向代理和负载均衡 |

## 单机部署步骤

### 步骤1：环境准备
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.9 python3.9-venv python3.9-dev
sudo apt install -y build-essential libssl-dev libffi-dev

# CentOS/RHEL
sudo yum install -y python39 python39-devel
sudo yum install -y gcc openssl-devel bzip2-devel libffi-devel

# Windows
# 1. 安装Python 3.9+ from python.org
# 2. 安装Visual Studio Build Tools
```

### 步骤2：获取代码
```bash
# 方法1：克隆仓库
git clone https://github.com/your-repo/xm-global-mt5.git
cd xm-global-mt5

# 方法2：下载发布包
wget https://github.com/your-repo/xm-global-mt5/releases/latest/download/release.tar.gz
tar -xzf release.tar.gz
cd xm-global-mt5
```

### 步骤3：安装依赖
```bash
# 创建虚拟环境
python3.9 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装生产环境额外依赖
pip install gunicorn psycopg2-binary redis
```

### 步骤4：配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
nano .env

# 关键配置项：
# USE_DEEPSEEK=true
# DEEPSEEK_API