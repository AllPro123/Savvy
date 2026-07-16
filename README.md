# Charlie 💜

**A standalone AI for your desktop terminal. She lives on *your* machine — no cloud, no fees, no data collection. Ever.**

Charlie is a single Python file with **zero dependencies** beyond Python itself. Her "brain" is any open-source language model you run locally (Ollama by default). She can hold conversations, read and write your files, search your code, run shell commands (with your permission), and remember things about you between sessions — everything a modern AI coding assistant does, entirely offline-capable and entirely free.

```
   ____ _                _ _
  / ___| |__   __ _ _ __| (_) ___
 | |   | '_ \ / _` | '__| | |/ _ \
 | |___| | | | (_| | |  | | |  __/
  \____|_| |_|\__,_|_|  |_|_|\___|
```

## The rules Charlie lives by

1. **Standalone.** One file. No accounts, no sign-ups, no API keys required.
2. **Never charges you.** Her default brain (Ollama) is free and open source.
3. **Never leaks your data.** All conversations, memory, and config live in `~/.charlie/` on your disk. There is no telemetry, no analytics, no phone-home code — you can read every line of `charlie.py` and verify it. Any request that would leave your machine asks you first.

## Quick start (5 minutes)

**1. Install Ollama** — the free, open-source engine that runs AI models locally:

- **macOS / Windows:** download from <https://ollama.com/download>
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

**2. Pull a model** (pick one for your hardware):

| Your machine | Command | Notes |
|---|---|---|
| 8 GB RAM | `ollama pull qwen2.5:3b` | small & quick |
| 16 GB RAM (recommended) | `ollama pull qwen2.5:7b` | great tool use — Charlie's default |
| 32 GB+ RAM / good GPU | `ollama pull qwen2.5:14b` or `llama3.1:8b` | smarter |

**3. Install & run Charlie:**

```sh
git clone https://github.com/AllPro123/Savvy.git
cd Savvy
sh install.sh
charlie
```

Or skip the install and just run her directly: `python3 charlie.py`

## What she can do

Talk to her like you'd talk to any assistant. She has real tools and uses them on her own:

- `read_file` / `write_file` / `edit_file` — work on your files
- `search_files` / `list_dir` — explore your projects
- `run_command` — run shell commands (**always asks you first**, unless you `/yolo`)
- `fetch_url` — pull a web page or API (**asks first** — it leaves your machine)
- `remember` — permanent local memory in `~/.charlie/memory.md`

Example session:

```
You ▸ what's eating my disk space in this folder?
  ⚙ run_command({"command": "du -sh * | sort -rh | head"})
  Allow? [y/N] y
Charlie ▸ Your `node_modules` is 1.2 GB — that's 90% of it. Want me to ...

You ▸ my name is Alex and I prefer tabs over spaces
  ⚙ remember({"note": "User's name is Alex; prefers tabs over spaces."})
Charlie ▸ Got it, Alex. Tabs it is — forever, or until you /forget me.
```

### Commands

| Command | What it does |
|---|---|
| `/model [name]` | show / switch the model |
| `/models` | list models installed in Ollama |
| `/provider [name]` | switch backend (ollama, lmstudio, llamacpp, vllm, localai, jan, ...) |
| `/providers` | list all configured backends |
| `/memory` / `/forget` | view / erase her long-term memory |
| `/yolo` | toggle auto-approval of shell commands |
| `/clear` | fresh conversation |
| `/save` | save the transcript to `~/.charlie/sessions/` |
| `/config` | show the config file |
| `/help` / `/exit` | you guessed it |

One-shot mode: `charlie "explain this error: ..."` answers and exits.

## Intertwining Charlie with other programs

Charlie speaks the standard OpenAI-compatible chat API, so she plugs into basically every open-source LLM server. Switch live with `/provider <name>`, or edit `~/.charlie/config.json`:

| Provider | Serve with | Charlie preset |
|---|---|---|
| **Ollama** (default) | `ollama serve` | `/provider ollama` |
| **LM Studio** | its "Local Server" tab (port 1234) | `/provider lmstudio` |
| **llama.cpp** | `llama-server -m model.gguf` (port 8080) | `/provider llamacpp` |
| **vLLM** | `vllm serve <model>` (port 8000) | `/provider vllm` |
| **LocalAI** | `local-ai run` | `/provider localai` |
| **Jan** | enable its API server (port 1337) | `/provider jan` |
| Anything else | any `/v1/chat/completions` endpoint | add it to `config.json` |

Adding your own is one JSON stanza:

```json
"providers": {
  "myserver": { "base_url": "http://localhost:5000/v1", "api_key": "", "model": "my-model" }
}
```

Models that handle Charlie's tools natively work best (qwen2.5, llama3.1, mistral-nemo, command-r). For models without native tool support, Charlie automatically falls back to a text-based tool protocol, so she stays functional either way.

### About Grok ⚠️

You asked for Grok, so a `grok` preset is included — **but it's off by default, and here's why:** Grok's API (api.x.ai) is a **paid cloud service run by xAI**. Using it means your prompts leave your machine and your card gets billed — which breaks Charlie's own rules. If you enable it anyway (put your xAI key in `config.json`, then `/provider grok`), Charlie will show you a clear warning every time she starts with it.

**The rule-abiding alternative:** xAI open-sourced the *weights* of Grok-1 and Grok-2. If you have serious hardware, you can run those locally through llama.cpp/vLLM and point Charlie at them — that's real Grok, with zero cloud and zero fees. For normal desktops, qwen2.5 or llama3.1 via Ollama will serve you far better.

## Privacy, verified

- **Config:** `~/.charlie/config.json`
- **Memory:** `~/.charlie/memory.md` (plain text — open it, edit it, delete it)
- **Saved chats:** `~/.charlie/sessions/`
- **Total uninstall:** delete `~/.charlie/` and `~/.local/bin/charlie`. Done.

The only network calls in the entire codebase are (1) to the model server *you* configured — localhost by default — and (2) the `fetch_url` tool, which asks your permission for every non-local URL. Search `charlie.py` for `http_request` to check for yourself.

## Requirements

- Python 3.9+ (preinstalled on macOS and nearly all Linux; on Windows use [python.org](https://python.org) or WSL)
- [Ollama](https://ollama.com) or any other local model server
- Enough RAM for the model you choose (see the table above)

---

*Charlie — she's yours, not theirs.*
