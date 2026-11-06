# yyds-gpt-image

通过 OpenAI 兼容的 `/v1` 图片接口生成或编辑图片。所有渠道（BaseURL + Key）都写在 `.env` 里，脚本本身不含任何凭据。

## 目录

```
yyds-gpt-image/
├── .env                 # 渠道凭据（不要外传）
├── SKILL.md             # Agent 使用说明
├── agents/openai.yaml
└── scripts/generate_image.py
```

## 配置 `.env`

一个渠道 = 一条 BaseURL + 一条 key，靠**变量名末尾的数字**区分编号：

```dotenv
# 渠道 1
YYDS_BASE_URL_1=https://yyds.chybenzun.top/v1
YYDS_API_KEY_1=sk-...
# YYDS_MODEL_1=gpt-image-2

# 渠道 2：前缀随意，只有末尾的 -2 有意义
0-0-BASE-URL-2=https://api.example.com/v1
0-0-API-KEY-2=sk-...

# 渠道 3
MY-BASE-URL-3=https://another.example.com/v1
MY-API-KEY-3=sk-...
```

规则：

- 变量名按 `-`、`_`、`.` 切词，最后一段是纯数字时作为渠道编号；编号前面的部分就是标签（`yyds`、`0-0`、`MY`），只用于可读性和消歧。
- `-` 与 `_` 等价：`YYDS_API_KEY_1` = `yyds-api-key-1`。
- 可识别后缀：`api-key` / `key` / `token`（密钥）、`base-url` / `base` / `url` / `host` / `endpoint`（接口地址）、`model`（模型名）。
- BaseURL 要带 `/v1` 根路径，脚本会拼接 `/images/generations` 或 `/images/edits`。
- `model` 缺省为 `gpt-image-2`；单独的 `*-model-N` 不会凭空创建渠道，只有该编号确实只有一个渠道时才生效。
- 渠道数量不限，写多少用多少。

加载顺序：`IMAGE_SKILL_ENV_FILE`（设置后替代技能内 `.env`）→ 技能内 `.env` → 当前目录 `./.env`（同名覆盖）。真实环境变量优先级最高。

## 选择渠道

| 方式 | 说明 |
| --- | --- |
| 不带参数 | 用编号最小的渠道（同编号按文件顺序） |
| `-n N` | 用编号 N 的渠道 |
| `--channel 0-0` | 按标签选，可与 `-n` 组合；同编号多标签时用它消歧 |
| `-l` | 列出所有渠道（key 打码），选中项标 `*`；也可 `-l -n 2` |

同编号存在多个标签时，`-n` 取 `.env` 中先出现的那个，并在 stderr 提示。

## 使用

生成：

```powershell
python "$env:USERPROFILE\.codex\skills\yyds-gpt-image\scripts\generate_image.py" `
  --prompt "A clean product photograph of a ceramic cup on a pale blue studio background" `
  --output .\output.png
```

换个渠道生成：

```powershell
python "$env:USERPROFILE\.codex\skills\yyds-gpt-image\scripts\generate_image.py" `
  --prompt "..." --output .\output.png -n 2
```

编辑（`--input` 为源图，`--reference` 可重复传参考图）：

```powershell
python "$env:USERPROFILE\.codex\skills\yyds-gpt-image\scripts\generate_image.py" `
  --prompt "Keep the subject and composition; replace the background with a warm paper texture" `
  --input .\source.png --reference .\style.png --output .\edited.png
```

其他参数：`--size`、`--quality`、`--background`、`--output-format`、`--timeout`（默认 600 秒）。

## 响应处理

服务端可能直接返回图片字节、URL 或 `b64_json`/`base64`/`data` 中的 base64，脚本会统一落盘到 `--output`，并自动创建父目录。返回 URL 时立即下载（链接可能过期）。成功时打印 `[标签#编号] 输出路径`。

## 常见问题

- `在 .env 里没有找到任何渠道`：检查 `BASE_URL`/`KEY` 是否都带了编号后缀。
- `渠道缺少 key 或 base_url`：该编号只有一半配置，或标签写岔了导致两条没有配对。
- `没有找到编号 N 的渠道`：用 `-l` 查看实际编号。
- `HTTP 4xx/5xx`：只输出截断后的服务端文本，不会回显 key。

`.env` 与脚本都请保持私有，不要提交或同步到公开仓库。
