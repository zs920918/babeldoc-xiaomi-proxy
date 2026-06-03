# BabelDOC Xiaomi MiMo Proxy

将 [BabelDOC](https://github.com/funstory-ai/BabelDOC)（PDF 翻译工具）接入小米内部 MiMo API 的协议转接代理。

## 原理

BabelDOC 使用 OpenAI Chat Completions API（`/v1/chat/completions`），小米内部 API 使用 Responses API（`/v1/responses`）。本代理在中间做协议转换：

```
BabelDOC ──Chat Completions──> localhost:8899 ──Responses API──> 小米内部API
         <──Chat Completions──                  <──Responses API──
```

## 快速开始

**前提：Python 3.10+**（其他依赖全部自动安装）

```bash
# 1. 克隆仓库
git clone https://github.com/zs920918/babeldoc-xiaomi-proxy.git
cd babeldoc-xiaomi-proxy

# 2. 安装代理依赖（仅 httpx）
pip install httpx

# 3. 翻译 PDF（首次运行会自动安装 BabelDOC，需要几分钟）
python translate.py 你的文件.pdf --api-key "你的API密钥"
```

首次运行会自动完成以下安装：
- 检测并安装 [uv](https://github.com/astral-sh/uv)（Python 包管理器）
- 通过 uv 安装 BabelDOC（含所有依赖，约 1GB）

## 常用命令

```bash
# 翻译指定页（不翻译封面）
python translate.py paper.pdf --pages 3-10 --api-key "sk-xxxxx"

# 指定输出目录
python translate.py paper.pdf -o ./output --api-key "sk-xxxxx"

# 只输出双语对照版（不要单语版）
python translate.py paper.pdf --no-mono --api-key "sk-xxxxx"

# 使用轻量模型（更快但质量稍低）
python translate.py paper.pdf --model xiaomi/mimo-v2-flash --api-key "sk-xxxxx"
```

## 参数一览

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | (必填) | 输入 PDF 文件路径 |
| `--api-key` | (必填) | API 密钥 |
| `--target-url` | `http://model.mify.ai.srv/v1` | API 地址 |
| `--model` | `xiaomi/mimo-v2.5-pro` | 模型名称 |
| `--lang-in` | `en` | 源语言 |
| `--lang-out` | `zh` | 目标语言 |
| `--proxy-port` | `8899` | 代理端口 |
| `--output` / `-o` | `.` | 输出目录 |
| `--qps` | `4` | 每秒请求数限制 |
| `--pages` | 全部 | 指定页码，如 `1,2,3-5` |
| `--no-mono` | false | 不输出单语 PDF |
| `--no-dual` | false | 不输出双语 PDF |

## 可用模型

| 模型名 | 说明 |
|--------|------|
| `xiaomi/mimo-v2.5-pro` | 旗舰模型，翻译质量最佳 |
| `xiaomi/mimo-v2-flash` | 轻量模型，速度快 |
| `xiaomi/mimo-v2-omni` | 多模态模型 |

## 单独使用代理

如果已安装 BabelDOC，可单独启动代理：

```bash
# 终端 1：启动代理
python proxy.py --target-url "http://model.mify.ai.srv/v1" --api-key "sk-xxxxx"

# 终端 2：用 BabelDOC 翻译
babeldoc --openai \
    --openai-model "xiaomi/mimo-v2.5-pro" \
    --openai-base-url "http://localhost:8899/v1" \
    --openai-api-key "sk-xxxxx" \
    --files input.pdf
```

## License

MIT
