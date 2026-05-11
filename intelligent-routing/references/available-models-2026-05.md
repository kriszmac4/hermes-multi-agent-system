# Available Models — Krisztian Setup

## Vertex AI (GCP) — Gemini models

List available: `~/.hermes/.venv/bin/python3 -c "from google import genai; c = genai.Client(vertexai=True, project='utility-meter-reader-492216', location='us-central1'); [print(m.name) for m in c.models.list() if 'gemini' in m.name.lower()]"`

### Working models (2026-05-03):
| Model ID | Vision | Notes |
|----------|--------|-------|
| `gemini-2.0-flash-001` | ❌ | Text only |
| `gemini-2.5-flash` | ✅ | **BEST for vision + text** |
| `gemini-2.5-flash-lite-001` | ❌? | Lite, faster |
| `gemini-2.5-pro` | ✅? | Pro tier |
| `gemini-2.5-computer-use-preview-10-2025` | ✅ | Computer use |
| `gemini-3-flash-preview` | ✅ | Latest flash |
| `gemini-3.1-flash-lite-preview` | ✅ | New lite |
| `gemini-3.1-pro-preview` | ✅ | Latest pro |

### Vision command:
```bash
~/.hermes/.venv/bin/python3 -c "
import base64
from google import genai
img_path = '/path/to/screenshot.png'
with open(img_path, 'rb') as f:
    img_data = base64.b64encode(f.read()).decode()
client = genai.Client(vertexai=True, project='utility-meter-reader-492216', location='us-central1')
r = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[{'role': 'user', 'parts': [
        {'inline_data': {'mime_type': 'image/png', 'data': img_data}},
        {'text': 'Extract all data...'}
    ]}]
)
print(r.text)
"
```

## OpenCode Zen — minimax-m2.5-free
- Current session model ✅
- No vision support (returns 404 on image input)

## OpenRouter
- `google/gemini-2.0-flash` — configured, has credit
- `nvidia/nemotron-3-super-120b-a12b` — configured

## GitHub Copilot
- ❌ Token issue: `ghp_*` (classic PAT) not accepted
- Need: `gho_*` (OAuth), `github_pat_*` (fine-grained with Copilot scope), or `ghu_*` (GitHub App)
- Not resolved yet
