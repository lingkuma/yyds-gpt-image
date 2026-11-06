#!/usr/bin/env python3
"""Generate or edit an image through one of several OpenAI-compatible channels.

All credentials live in `.env`. Every variable is grouped into a channel by a
trailing number, so `-n N` picks the channel and the prefix is free-form label
text (`YYDS_API_KEY_1`, `yyds-api-key-1`, `0-0-api-key-2`, ...).
"""

import argparse
import base64
import json
import mimetypes
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
import uuid


DEFAULT_MODEL = "gpt-image-2"
SPLIT_RE = re.compile(r"[-_.\s]+")
KINDS = {
    ("api", "key"): "key",
    ("apikey",): "key",
    ("key",): "key",
    ("token",): "key",
    ("base", "url"): "url",
    ("baseurl",): "url",
    ("endpoint",): "url",
    ("url",): "url",
    ("base",): "url",
    ("host",): "url",
    ("model",): "model",
}


def die(message):
    raise SystemExit(f"yyds-gpt-image: {message}")


def env_files():
    explicit = os.getenv("IMAGE_SKILL_ENV_FILE")
    skill_env = pathlib.Path(__file__).resolve().parents[1] / ".env"
    candidates = [pathlib.Path(explicit).expanduser()] if explicit else [skill_env]
    candidates.append(pathlib.Path.cwd() / ".env")
    seen, files = set(), []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        files.append(resolved)
    return files


def read_env_file(path):
    values = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        die(f"could not read {path}: {exc}")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if name:
            values[name] = value
    return values


def parse_variable(name):
    """Split `yyds-api-key-1` into ("yyds", "key", 1). Return None if irrelevant."""
    tokens = [token for token in SPLIT_RE.split(name.strip()) if token]
    if not tokens:
        return None
    index = 1
    if tokens[-1].isdigit():
        index = int(tokens.pop())
    if not tokens:
        return None
    lowered = [token.lower() for token in tokens]
    for size in (2, 1):
        if len(lowered) < size:
            continue
        kind = KINDS.get(tuple(lowered[-size:]))
        if kind:
            label = "-".join(tokens[:-size]) or "default"
            return label, kind, index
    return None


def collect_channels():
    entries = {}
    files = env_files()
    for path in files:
        entries.update(read_env_file(path))
    for name in entries:
        if name in os.environ:
            entries[name] = os.environ[name]

    channels, models, order = {}, {}, 0
    for name, value in entries.items():
        parsed = parse_variable(name)
        if not parsed:
            continue
        label, kind, index = parsed
        identity = (label.lower(), index)
        channel = channels.get(identity)
        if channel is None:
            channel = channels[identity] = {
                "label": label,
                "index": index,
                "order": order,
                "key": None,
                "url": None,
                "model": None,
            }
            order += 1
        if not value:
            continue
        channel[kind] = value
        if kind == "model":
            models.setdefault(index, set()).add(value)

    # A `*-model-N` line alone does not define a channel; use it only when the
    # index maps to exactly one real channel.
    real = [item for item in channels.values() if item["key"] or item["url"]]
    for item in real:
        hints = models.get(item["index"], set())
        if not item["model"] and len(hints) == 1 and len(
            [other for other in real if other["index"] == item["index"]]
        ) == 1:
            item["model"] = next(iter(hints))
    return sorted(real, key=lambda item: (item["index"], item["order"]))


def channel_name(channel):
    return f"{channel['label']}#{channel['index']}"


def mask(value):
    if not value:
        return "(未配置)"
    if len(value) <= 12:
        return value[:3] + "***"
    return value[:6] + "***" + value[-3:]


def describe(channel):
    return (
        f"{channel_name(channel)} <- base_url={channel['url'] or '(未配置)'} "
        f"key={mask(channel['key'])}"
    )


def print_channels(channels, selected):
    if not channels:
        die(f"在 .env 里没有找到任何渠道，请检查 {', '.join(str(p) for p in env_files()) or '环境文件'}")
    for channel in channels:
        marker = "*" if channel is selected else " "
        model = channel["model"] or DEFAULT_MODEL
        print(
            f"{marker} [{channel['index']}] {channel_name(channel):<20} "
            f"base_url={channel['url'] or '(未配置)':<40} "
            f"key={mask(channel['key']):<14} model={model}"
        )


def select_channel(channels, index, label):
    pool = channels
    if label:
        pool = [item for item in pool if item["label"].lower() == label.lower()]
        if not pool:
            die(f"没有找到标签为 '{label}' 的渠道，用 -l 查看可用渠道")
    if index is not None:
        pool = [item for item in pool if item["index"] == index]
        if not pool:
            available = ", ".join(str(i) for i in sorted({item["index"] for item in channels})) or "无"
            die(f"没有找到编号 {index} 的渠道，可用编号: {available}")
    if not pool:
        die("在 .env 里没有找到任何渠道")

    complete = [item for item in pool if item["key"] and item["url"]]
    if not complete:
        details = "; ".join(describe(item) for item in pool)
        die(f"渠道缺少 key 或 base_url: {details}")

    chosen = complete[0]
    if len(complete) > 1 and complete[1]["index"] == chosen["index"]:
        print(
            "yyds-gpt-image: 编号 "
            f"{chosen['index']} 存在多个渠道 ({', '.join(channel_name(i) for i in complete)})，"
            f"使用 {channel_name(chosen)}；可用 -n 唯一编号或 --channel 指定标签",
            file=sys.stderr,
        )
    return chosen


def request(url, data, headers, timeout):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.headers.get_content_type(), response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:800]
        die(f"HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        die(f"request failed: {exc.reason}")


def find_image(payload):
    if isinstance(payload, dict):
        for key in ("b64_json", "base64", "data"):
            value = payload.get(key)
            if isinstance(value, str) and len(value) > 100:
                return "base64", value
        for key in ("url", "image_url"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return "url", value
        for value in payload.values():
            found = find_image(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find_image(value)
            if found:
                return found
    return None


def multipart(fields, files):
    boundary = "----codex-" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    for name, path in files:
        source = pathlib.Path(path)
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        chunks.extend(
            [
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{source.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode(),
                source.read_bytes(),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def main():
    parser = argparse.ArgumentParser(
        description="通过 .env 中配置的任意渠道生成或编辑图片（默认使用第一个渠道）。"
    )
    parser.add_argument("--prompt")
    parser.add_argument("--output")
    parser.add_argument("--input")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--size", default="auto")
    parser.add_argument("--quality", default="auto")
    parser.add_argument("--background", default="auto")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "-n",
        "--index",
        type=int,
        help="使用编号为 N 的渠道（对应 .env 名字末尾的 -N）；默认第一个",
    )
    parser.add_argument("--channel", help="按标签名选择渠道，例如 yyds 或 0-0")
    parser.add_argument("-l", "--list", action="store_true", help="列出所有渠道后退出")
    args = parser.parse_args()

    channels = collect_channels()
    if args.list:
        chosen = None
        if args.index is not None or args.channel:
            try:
                chosen = select_channel(channels, args.index, args.channel)
            except SystemExit as exc:
                print(exc, file=sys.stderr)
        print_channels(channels, None if chosen is None else chosen)
        return
    if not args.prompt:
        parser.error("--prompt is required")
    if not args.output:
        parser.error("--output is required")

    channel = select_channel(channels, args.index, args.channel)
    key = channel["key"]
    base = channel["url"].rstrip("/")
    model = channel["model"] or DEFAULT_MODEL

    if args.input:
        fields = {"model": model, "prompt": args.prompt, "size": args.size}
        files = [("image[]", args.input)] + [("image[]", path) for path in args.reference]
        body, content_type = multipart(fields, files)
        headers = {"Authorization": f"Bearer {key}", "Content-Type": content_type}
        response_type, raw = request(base + "/images/edits", body, headers, args.timeout)
    else:
        payload = {
            "model": model,
            "prompt": args.prompt,
            "size": args.size,
            "quality": args.quality,
            "background": args.background,
            "output_format": args.output_format,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        response_type, raw = request(
            base + "/images/generations", json.dumps(payload).encode(), headers, args.timeout
        )

    if response_type.startswith("image/"):
        image = raw
    else:
        try:
            found = find_image(json.loads(raw))
        except json.JSONDecodeError:
            die("provider returned non-image, non-JSON data")
        if not found:
            die("provider response did not contain an image")
        kind, value = found
        if kind == "url":
            try:
                image_request = urllib.request.Request(
                    value,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
                    },
                )
                image = urllib.request.urlopen(image_request, timeout=args.timeout).read()
            except Exception as exc:
                die(f"could not download image URL: {exc}")
        else:
            try:
                image = base64.b64decode(value.split(",", 1)[-1])
            except (ValueError, base64.binascii.Error) as exc:
                die(f"invalid base64 image response: {exc}")

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    print(f"[{channel_name(channel)}] {output}")


if __name__ == "__main__":
    main()
