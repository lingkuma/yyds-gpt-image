---
name: yyds-gpt-image
description: Generate or edit raster images through the YYDS OpenAI-compatible GPT Image API. Use when Codex needs to call yyds.chybenzun.top for text-to-image generation, image edits, or edits with additional reference images, and save the returned image locally.
---

# YYDS GPT Image

Use the bundled `scripts/generate_image.py` for both generation and editing. The
service exposes an OpenAI-style `/v1` API and currently serves `gpt-image-2`.
Never put an API key in prompts, source files, or logs; the script has no
built-in credentials and reads everything from `.env`.

## Channels in `.env`

Every channel is one BaseURL plus one key, identified by the trailing `-N`:

```dotenv
# channel 1
YYDS_BASE_URL_1=https://yyds.chybenzun.top/v1
YYDS_API_KEY_1=sk-...
# YYDS_MODEL_1=gpt-image-2

# channel 2 - prefix is free-form, only the trailing number matters
0-0-BASE-URL-2=https://api.example.com/v1
0-0-API-KEY-2=sk-...

# channel 3
MY-BASE-URL-3=https://another.example.com/v1
MY-API-KEY-3=sk-...
```

- Variable names are split on `-`, `_`, `.`; the last token that is a number is
  the channel number, the token(s) before it are the label.
- The label is free text (`yyds`, `0-0`, `MY`), used only for readability and
  disambiguation. Recognized suffixes: `api-key`/`key`/`token`,
  `base-url`/`base`/`url`/`host`/`endpoint`, `model`. `-` and `_` both work, so
  `YYDS_API_KEY_1` equals `yyds-api-key-1`.
- Add as many channels as needed. `*-model-N` is optional (default
  `gpt-image-2`) and never creates a channel on its own.
- The BaseURL must include the `/v1` root.

## Selecting a channel

- Default: the lowest channel number (file order breaks ties).
- `-n N`: use channel number `N`. If two labels share the number, the first in
  file order wins and a hint is printed on stderr.
- `--channel LABEL`: pick by label, e.g. `--channel 0-0`, combinable with `-n`.
- `-l` (optionally `-l -n 2` or `-l --channel 0-0`): list channels with masked
  keys; the selected one is marked with `*`.

Load order: `IMAGE_SKILL_ENV_FILE` (if set, replaces the skill file) then the
skill's own `.env`, then `./.env` of the current directory, which overrides
same-named entries. Real environment variables override values from the files.

Keep credential files and source code private; do not commit or sync them. Ask
for a channel only when `.env` defines none.

## Generate

```powershell
python "$env:USERPROFILE\.codex\skills\yyds-gpt-image\scripts\generate_image.py" `
  --prompt "A clean product photograph of a ceramic cup on a pale blue studio background" `
  --output .\output.png
```

Add `-n 2` (or `--channel 0-0`) to use another channel. Generation posts JSON
to `/images/generations`. The script supports `--size`, `--quality`,
`--background`, `--output-format`, and `--timeout`.

## Edit

Pass one source image with `--input`; add one or more optional references with
repeated `--reference` flags:

```powershell
python "$env:USERPROFILE\.codex\skills\yyds-gpt-image\scripts\generate_image.py" `
  --prompt "Keep the subject and composition; replace the background with a warm paper texture" `
  --input .\source.png --reference .\style.png --output .\edited.png
```

Edits post multipart form data to `/images/edits`, using the official repeated
`image[]` field for the source and reference files. Treat non-2xx responses as
failures and report only sanitized provider text. If the provider returns a URL,
download it immediately because image URLs may expire.

## Response handling

The provider may return raw image bytes, a URL, or base64 under common keys such
as `b64_json`, `base64`, or nested `data`. The script normalizes all of these to
the requested output path and creates parent directories as needed. On success
it prints `[label#N] <output path>` so the used channel stays visible.
