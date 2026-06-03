# BabelDOC Xiaomi MiMo Proxy

将 BabelDOC（PDF 翻译工具）接入小米内部 MiMo API 的协议转接代理。

## 原理

BabelDOC 使用 OpenAI Chat Completions API 格式，小米内部 API 使用 Responses API 格式。本代理在中间做协议转换：

```
BabelDOC ──Chat Completions──> localhost:8899 ──Responses API──> 小米内部API
         <──Chat Completions──                  <──Responses API──
```

## 快速开始

### 1. 安装依赖

```bash
pip install httpx
```

BabelDOC 会在首次运行时自动安装（通过 uv）。

### 2. 配置 API

编辑 `translate.py`，找到以下参数并填入你的实际值：

| 参数 | 说明 | 在哪里改 |
|------|------|----------|
| `--target-url` | 小米内部 API 地址 | 命令行参数 |
| `--api-key` | API 密钥 | 命令行参数 |

### 3. 翻译 PDF

```bash
# 翻译整个文件
python translate.py input.pdf --api-key "你的密钥"

# 只翻译指定页
python translate.py input.pdf --pages 7-10 --api-key "你的密钥"

# 指定语言和输出目录
python translate.py input.pdf --lang-in en --lang-out zh -o ./output --api-key "你的密钥"
```

## 单独使用代理

如果你已经安装了 BabelDOC，可以单独启动代理：

```bash
# 终端 1：启动代理
python proxy.py --target-url "http://你的API地址/v1" --api-key "你的密钥"

# 终端 2：用 BabelDOC 翻译
babeldoc --openai \
    --openai-model "xiaomi/mimo-v2.5-pro" \
    --openai-base-url "http://localhost:8899/v1" \
    --openai-api-key "你的密钥" \
    --files input.pdf
```

## 参数说明

### translate.py

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | (必填) | 输入 PDF 文件路径 |
| `--model` | `xiaomi/mimo-v2.5-pro` | 模型名称 |
| `--lang-in` | `en` | 源语言 |
| `--lang-out` | `zh` | 目标语言 |
| `--api-key` | (必填) | API 密钥 |
| `--target-url` | `http://model.mify.ai.srv/v1` | API 地址 |
| `--proxy-port` | `8899` | 代理端口 |
| `--output` / `-o` | `.` | 输出目录 |
| `--qps` | `4` | 每秒请求数限制 |
| `--pages` | 全部 | 指定页码，如 `1,2,3-5` |
| `--no-mono` | false | 不输出单语 PDF |
| `--no-dual` | false | 不输出双语 PDF |

### proxy.py

| 参数 | 说明 |
|------|------|
| `--port` | 代理监听端口（默认 8899） |
| `--target-url` | 目标 API 基础地址（必填） |
| `--api-key` | 默认 API 密钥 |

## 可用模型

| 模型名 | 说明 |
|--------|------|
| `xiaomi/mimo-v2.5-pro` | 旗舰模型，翻译质量最佳 |
| `xiaomi/mimo-v2-flash` | 轻量模型，速度快 |
| `xiaomi/mimo-v2-omni` | 多模态模型 |

## License

MIT
