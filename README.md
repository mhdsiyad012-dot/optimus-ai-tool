# ⚡ Optimus AI — Autonomous Global AI Directory & 24/7 Discovery Assistant

> **A production-ready, 100% free-to-run system that catalogs historical and newly released AI tools hierarchically by parent company, eliminates frontend API rate limits forever, and continuously discovers global AI breakthroughs 24/7 at $0 cost.**

---

## 🎯 Problem Statement & Architectural Solution

### The Rate Limit Problem
Previously, websites calling the Google Gemini AI Studio or OpenAI API directly on user queries suffered from:
1. **Immediate HTTP 429 Rate Limits** when concurrent visitors entered searches.
2. **Exhausted Free-Tier Quotas** resulting in service blackouts.
3. **High Latency** for every visitor waiting for LLM completions.

### The Optimus AI Zero-Cost Solution
Optimus AI decouples user query serving from LLM inference:
1. **Zero-Latency Static Directory (`data/ai_directory.json`)**: Visitors browse, search, and filter an indexed database client-side. Response times are sub-millisecond, and frontend API rate limits are eliminated forever.
2. **Optimus Spark 24/7 Agent**: A background autonomous agent continuously monitors global AI news feeds, research blogs, and developer hubs.
3. **Zero-Cost Multi-Provider LLM Rotator (`agent/llm_router.py`)**: Uses a resilient priority fallback queue (Google Gemini with multi-key rotation → Groq Llama 3.3 70B → OpenRouter Free → Local Ollama → Offline Heuristic Extractor) ensuring 100% uptime with no halts.
4. **Autonomous Cloud Sync via GitHub Actions (`.github/workflows/optimus_24_7_agent.yml`)**: Runs hands-free every 6 hours on GitHub's free runners, automatically committing newly verified AI tools to GitHub so the live website stays continually updated.

---

## 🏗️ Repository Architecture

```
optimus-ai/
├── .github/
│   └── workflows/
│       └── optimus_24_7_agent.yml   # 24/7 scheduled discovery & auto-commit workflow
├── agent/
│   ├── __init__.py                  # Package initializer
│   ├── llm_router.py                # Multi-provider LLM rotator & Pydantic validator
│   ├── web_researcher.py            # Free RSS, DDG, and Jina web scraper engine
│   └── optimus_assistant.py         # Autonomous manager (daemon, cron, backfill, CLI)
├── data/
│   ├── ai_directory.json            # Master hierarchical database (60+ initial tools)
│   └── changelog.md                 # Autonomous discovery audit log
├── web/
│   ├── index.html                   # High-tech cyber obsidian web frontend
│   ├── styles.css                   # Responsive Vanilla CSS with glassmorphism
│   └── app.js                       # Client-side search, ecosystem view, and studio drawer
├── .env.example                     # Environment variables and multi-key rotation template
├── requirements.txt                 # Python dependencies (requests, bs4, feedparser, pydantic)
└── README.md                        # Documentation and architecture guide
```

---

## 📊 Strict Tool Schema (`data/ai_directory.json`)

Every tool entry adheres strictly to this Pydantic-validated schema:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique kebab-case slug (e.g., `google-antigravity`) |
| `name` | `string` | Official product or tool name |
| `parent_org` | `string` | Parent company or creator ecosystem |
| `category` | `string` | Standardized category (e.g., `Autonomous Agents & Coding`) |
| `release_date` | `string` | ISO format (`YYYY-MM-DD` or `YYYY-MM`) |
| `status` | `string` | `Active`, `Beta`, `Deprecated`, or `Experimental` |
| `pricing` | `string` | `Free`, `Freemium`, `Paid`, or `Open Source` |
| `official_url` | `string` | Direct website, documentation, or repository URL |
| `short_description` | `string` | 1-2 sentence high-impact summary |
| `key_features` | `string[]` | List of 3-5 core capabilities |
| `tags` | `string[]` | Keywords for multi-attribute search |
| `last_verified` | `string` | Date of last verification (`YYYY-MM-DD`) |

### Pre-Populated Major Ecosystems
The initial master seed comes pre-configured with 60+ tools across:
- **Google**: Google Antigravity, Google Stitch, Google AI Studio, Gemini, Google Veo, NotebookLM, Imagen 3, Gemma.
- **OpenAI**: ChatGPT, GPT-4o, OpenAI o1, Sora, Whisper, OpenAI Swarm.
- **Anthropic**: Claude 3.5 Sonnet, Claude Computer Use, Model Context Protocol (MCP), Claude 3.5 Haiku.
- **Meta**: Llama 3.3 70B, SAM 2, Movie Gen, AudioCraft.
- **Microsoft**: Microsoft Copilot, AutoGen, Phi-4, Semantic Kernel.
- **Mistral AI**: Mistral Large 2, Codestral, Le Chat.
- **DeepSeek**: DeepSeek-V3, DeepSeek-R1, DeepSeek Coder V2.
- **xAI**: Grok 2, Grok 3.
- **Hugging Face**: Hugging Face Hub, Transformers, SmolLM.
- **Stability AI**: Stable Diffusion 3.5, Stable Audio 2.0.
- **Midjourney**: Midjourney v6.1.
- **Perplexity**: Perplexity Search, Perplexity Sonar API.
- **ElevenLabs**: ElevenLabs Voice AI, ElevenReader.
- **Runway**: Runway Gen-3 Alpha, Runway Act-One.
- **Cursor**: Cursor AI Code Editor.
- **OpenCode**: OpenCode Agent Framework.

---

## ⚡ Quick Start

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/optimus-ai.git
cd optimus-ai
pip install -r requirements.txt
```

### 2. Configure Environment (Optional but Recommended)
Copy the example environment file:
```bash
cp .env.example .env
```
Edit `.env` and add your free API keys. You can specify **multiple comma-separated keys** to enable automatic 429 key rotation:
```ini
GEMINI_API_KEY=key_one,key_two,key_three
GROQ_API_KEY=gsk_key1,gsk_key2
OPENROUTER_API_KEY=sk-or-v1-key
```

> **Note**: Even if you provide 0 API keys, Optimus AI gracefully uses its deterministic heuristic extraction fallback and local Ollama, ensuring tests and runs never crash.

---

## 🚀 Autonomous Execution Modes

### Mode A: Autonomous Scheduled Sync (`--cron`)
Pulls the latest RSS/Atom streams (Hacker News AI, Google AI Blog, OpenAI News, Hugging Face), scrapes candidate links, extracts schema-compliant JSON, and merges into `data/ai_directory.json`:
```bash
python agent/optimus_assistant.py --cron
```

### Mode B: Deep Historical Backfill (`--backfill`)
Searches the web for every AI tool released by a specific company or category, extracting profiles and merging them into the tree:
```bash
# Backfill Google ecosystem
python agent/optimus_assistant.py --backfill "Google"

# Backfill DeepSeek models
python agent/optimus_assistant.py --backfill "DeepSeek"

# Backfill a category
python agent/optimus_assistant.py --backfill "Autonomous Coding Agents"
```

### Mode C: 24/7 Autonomous Daemon (`--daemon`)
Runs continuously in the background, executing discovery cycles every 6 hours (or custom `--interval`):
```bash
python agent/optimus_assistant.py --daemon --interval 21600
```

### Mode D: Interactive Assistant Studio CLI (`--interactive`)
Launches the interactive terminal assistant where you can paste URLs, inspect tools, and run backfills interactively:
```bash
python agent/optimus_assistant.py --interactive
```

### Mode E: Safe Dry-Run (`--dry-run`)
Executes the full pipeline without making external LLM API calls, verifying the deduplication, merging, and logging logic:
```bash
python agent/optimus_assistant.py --cron --dry-run
```

---

## 🌐 Launching the Web Frontend

Serve the web directory using Python's built-in HTTP server:
```bash
python -m http.server 8000 --directory web
```
Open [http://localhost:8000](http://localhost:8000) in your browser.

### Key Web Features:
- **Instant Search (`Ctrl+K`)**: Multi-attribute filtering across names, parent companies, tags, descriptions, and features.
- **Company Ecosystem View**: Searching or clicking "Google", "Anthropic", etc. displays an interactive organization header with dedicated tool breakdown.
- **Radar Ticker**: Highlights newly verified AI releases.
- **Optimus Assistant Studio Drawer**: Interactive admin panel to paste raw text or URLs, generate structured JSON, and inject into the active view.
- **Exporting**: One-click download of the entire directory in JSON or CSV.
- **Offline / Local Fallback**: Built-in seed cache ensures the UI functions flawlessly even when opened directly as a `file://`.

---

## 🤖 24/7 Cloud Automation via GitHub Actions

The included workflow `.github/workflows/optimus_24_7_agent.yml`:
1. Executes on a cron schedule every 6 hours (`0 */6 * * *`).
2. Supports manual trigger with optional `backfill_query` via GitHub's "Run workflow" button.
3. Automatically commits and pushes updated `data/ai_directory.json` and `data/changelog.md` back to your repo.

### Setup GitHub Secrets:
In your GitHub Repository, navigate to **Settings > Secrets and variables > Actions** and add:
- `GEMINI_API_KEY`: Your Gemini API keys (comma-separated for rotation).
- `GROQ_API_KEY`: Your Groq API keys.
- `OPENROUTER_API_KEY`: Your OpenRouter API key.

---

## 🛡️ License & Credits
- Built with Google Antigravity & DeepMind research principles.
- Free and open for developers, researchers, and creators worldwide.
