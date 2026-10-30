"""全局配置"""
import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据库
DB_PATH = BASE_DIR / "data" / "ai_text.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# 文件存储
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
PDF_DIR = BASE_DIR / "data" / "pdfs"

# 确保目录存在
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

# 爬虫配置
CRAWLER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
CRAWLER_TIMEOUT = 30
CRAWLER_MAX_RESULTS = 20  # 每个关键词每次采集的最大结果数
CRAWLER_MAX_FILE_SIZE = 50 * 1024 * 1024
CRAWLER_MAX_CONTENT_LENGTH = 200_000
CRAWLER_RETRIES = 2
CRAWLER_REQUEST_INTERVAL = 2.0  # 同一域名至少间隔 2 秒
CRAWLER_SEARCH_REQUEST_INTERVAL = 15.0
CRAWLER_SEARCH_COOLDOWN_SECONDS = 12 * 60 * 60
CRAWLER_RESPECT_ROBOTS_TXT = True  # 遵守 robots.txt 协议（合规默认开启）
CRAWLER_ROBOTS_FAIL_CLOSED = True  # 无法确认规则时停止抓取，不冒险放行
CRAWLER_ROBOTS_CACHE_SECONDS = 6 * 60 * 60
CRAWLER_ROBOTS_FAILURE_CACHE_SECONDS = 10 * 60

# 首次启动时写入 SQLite 的数据源。权威站点只允许使用自身公开的
# API、RSS 或目录适配器发现内容，通用搜索仅在用户明确选择时运行。
DEFAULT_DATA_SOURCES = [
    {
        "name": "中国政府网",
        "source_kind": "official",
        "base_url": "https://www.gov.cn",
        "domain": "gov.cn",
        "priority": 10,
        "config": {"description": "国务院及国家层面政策文件"},
    },
    {
        "name": "国家数据局",
        "source_kind": "official",
        "base_url": "https://www.nda.gov.cn",
        "domain": "nda.gov.cn",
        "priority": 12,
        "config": {"description": "数据基础制度、数据要素与数字经济政策"},
    },
    {
        "name": "工业和信息化部",
        "source_kind": "official",
        "base_url": "https://www.miit.gov.cn",
        "domain": "miit.gov.cn",
        "priority": 15,
        "config": {"description": "工业制造、人工智能及信息化政策"},
    },
    {
        "name": "国家发展改革委",
        "source_kind": "official",
        "base_url": "https://www.ndrc.gov.cn",
        "domain": "ndrc.gov.cn",
        "priority": 18,
        "config": {"description": "发展规划、产业与重大政策"},
    },
    {
        "name": "国务院国资委",
        "source_kind": "official",
        "base_url": "https://www.sasac.gov.cn",
        "domain": "sasac.gov.cn",
        "priority": 20,
        "config": {"description": "中央企业、产业数字化与人工智能应用"},
    },
    {
        "name": "中国信息通信研究院",
        "source_kind": "official",
        "base_url": "https://www.caict.ac.cn",
        "domain": "caict.ac.cn",
        "priority": 25,
        "config": {"description": "白皮书、研究报告与行业实践"},
    },
    {
        "name": "国家标准化管理委员会",
        "source_kind": "official",
        "base_url": "https://www.sac.gov.cn",
        "domain": "sac.gov.cn",
        "priority": 28,
        "config": {"description": "标准化政策、标准公告及公开信息"},
    },
    {
        "name": "Bing网页搜索（补充）",
        "source_kind": "search",
        "base_url": "https://www.bing.com/search",
        "domain": "",
        "priority": 90,
        "config": {"engine": "bing", "description": "通用网络发现，仅作为补充来源"},
    },
    {
        "name": "百度网页搜索（补充）",
        "source_kind": "search",
        "base_url": "https://www.baidu.com/s",
        "domain": "",
        "priority": 91,
        "config": {"engine": "baidu", "description": "通用网络发现，仅作为补充来源"},
    },
]

# 定时任务
SCHEDULER_ENABLED = True
SCHEDULER_HOUR = 8  # 每天早上8点执行
SCHEDULER_MINUTE = 0
SCHEDULER_CHECK_MINUTES = 30

# AI 提供商预设
PROVIDER_PRESETS = {
    "nvidia": {
        "name": "Nvidia NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "type": "preset",
        "website": "https://build.nvidia.com",
        "description": "NVIDIA 推理微服务 · OpenAI 兼容格式",
        "context_window": 0,  # 0 = 自动
    },
    "moonshot": {
        "name": "Kimi / Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "type": "preset",
        "website": "https://platform.moonshot.cn",
        "description": "月之暗面 Kimi 系列",
        "context_window": 128000,
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "type": "preset",
        "website": "https://ai.google.dev",
        "description": "Google Gemini 系列 (OpenAI 兼容端点)",
        "context_window": 0,
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "type": "preset",
        "website": "https://platform.deepseek.com",
        "description": "深度求索 DeepSeek 系列",
        "context_window": 64000,
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "type": "preset",
        "website": "https://platform.minimaxi.com",
        "description": "MiniMax 系列",
        "context_window": 245760,
    },
    "dashscope": {
        "name": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "type": "preset",
        "website": "https://bailian.console.aliyun.com",
        "description": "通义千问系列 · API 按量付费",
        "context_window": 0,
    },
    "qianfan": {
        "name": "百度智能云千帆",
        "base_url": "https://qianfan.baidubce.com/v2",
        "type": "preset",
        "website": "https://cloud.baidu.com/product/wenxinworkshop",
        "description": "文心一言系列",
        "context_window": 0,
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "type": "preset",
        "website": "https://siliconflow.cn",
        "description": "硅基流动 · 多模型聚合",
        "context_window": 0,
    },
    "volcano": {
        "name": "火山方舟",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "type": "preset",
        "website": "https://www.volcengine.com/product/ark",
        "description": "字节跳动 · 豆包系列",
        "context_window": 0,
    },
    "stepfun": {
        "name": "阶跃星辰",
        "base_url": "https://api.stepfun.com/v1",
        "type": "preset",
        "website": "https://platform.stepfun.com",
        "description": "Step 系列",
        "context_window": 0,
    },
    "modelscope": {
        "name": "魔搭 ModelScope",
        "base_url": "https://api-inference.modelscope.cn/v1",
        "type": "preset",
        "website": "https://modelscope.cn",
        "description": "阿里达摩院 ModelScope",
        "context_window": 0,
    },
    "sensenova": {
        "name": "商汤日日新",
        "base_url": "https://api.sensenova.cn/compatible-mode/v1",
        "type": "preset",
        "website": "https://platform.sensenova.cn",
        "description": "商汤 SenseNova 系列",
        "context_window": 0,
    },
    "hunyuan": {
        "name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "type": "preset",
        "website": "https://cloud.tencent.com/product/hunyuan",
        "description": "腾讯混元大模型",
        "context_window": 0,
    },
    "mimo": {
        "name": "小米 MiMo",
        "base_url": "https://api.mimo.xiaomi.com/v1",
        "type": "preset",
        "website": "https://mimo.xiaomi.com",
        "description": "小米 MiMo 系列",
        "context_window": 0,
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "type": "preset",
        "website": "https://open.bigmodel.cn",
        "description": "智谱 AI · GLM 系列",
        "context_window": 128000,
    },
    "openai": {
        "name": "OpenAI API",
        "base_url": "https://api.openai.com/v1",
        "type": "preset",
        "website": "https://platform.openai.com",
        "description": "GPT 系列",
        "context_window": 0,
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com/v1",
        "type": "preset",
        "website": "https://console.anthropic.com",
        "description": "Claude 系列",
        "context_window": 200000,
    },
    "grok": {
        "name": "xAI Grok",
        "base_url": "https://api.x.ai/v1",
        "type": "preset",
        "website": "https://x.ai",
        "description": "xAI Grok 系列",
        "context_window": 0,
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "type": "preset",
        "website": "https://openrouter.ai",
        "description": "多模型聚合路由",
        "context_window": 0,
    },
}

# 本地部署预设
LOCAL_PRESETS = {
    "ollama": {
        "name": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "type": "local",
        "description": "本地部署 Ollama",
        "context_window": 0,
        "default_model": "qwen2.5:7b",
    },
    "lmstudio": {
        "name": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "type": "local",
        "description": "本地部署 LM Studio",
        "context_window": 0,
        "default_model": "qwen2.5-coder:7b",
    },
    "vllm": {
        "name": "vLLM",
        "base_url": "http://127.0.0.1:8000/v1",
        "type": "local",
        "description": "本地部署 vLLM",
        "context_window": 0,
        "default_model": "",
    },
}

# CORS
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

# 邮件 SMTP 配置 — 用于注册验证码和采集通知
# 敏感信息（邮箱、授权码）一律通过环境变量注入，切勿硬编码提交到仓库：
#   SMTP_ENABLED / SMTP_HOST / SMTP_PORT / SMTP_USE_SSL / SMTP_USERNAME / SMTP_PASSWORD / SMTP_SENDER_NAME
# 未配置 SMTP_USERNAME / SMTP_PASSWORD 时邮件服务自动禁用。
SMTP_CONFIG = {
    "enabled": os.getenv("SMTP_ENABLED", "false").lower() == "true",
    "host": os.getenv("SMTP_HOST", "smtp.qq.com"),      # SMTP 服务器地址
    "port": int(os.getenv("SMTP_PORT", "465")),         # SMTP 端口 (SSL: 465, TLS: 587)
    "use_ssl": os.getenv("SMTP_USE_SSL", "true").lower() == "true",
    "username": os.getenv("SMTP_USERNAME", ""),         # 发件邮箱地址 (如: your_email@qq.com)
    "password": os.getenv("SMTP_PASSWORD", ""),         # SMTP 授权码 (不是邮箱登录密码)
    "sender_name": os.getenv("SMTP_SENDER_NAME", "策知系统"),   # 发件人显示名称
}

# 验证码有效期（分钟）
VERIFY_CODE_EXPIRE_MINUTES = 10
