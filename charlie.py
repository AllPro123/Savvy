#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Charlie — a standalone, local-first AI agent for your terminal.

  * Runs entirely on YOUR machine. No accounts, no subscriptions, no telemetry.
  * Default brain: Ollama (free, open source, local).
  * Also speaks to any OpenAI-compatible server: LM Studio, llama.cpp,
    vLLM, LocalAI, Jan, KoboldCpp ... and (optionally, disabled by default)
    cloud endpoints like xAI Grok if YOU choose to add a key.
  * Agent tools: read/write/edit files, search code, list directories,
    run shell commands (with your confirmation), fetch URLs, and a
    persistent local memory.

Zero third-party dependencies. Python 3.9+ standard library only.

Usage:
    python3 charlie.py            # start chatting
    python3 charlie.py "question" # one-shot answer, then exit
    charlie                       # if installed via install.sh

All of Charlie's data lives in ~/.charlie/ — delete that folder and every
trace of her memory is gone. Nothing is ever uploaded anywhere unless you
explicitly configure a remote provider.
"""

import datetime
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Paths & configuration
# --------------------------------------------------------------------------

CHARLIE_HOME = os.path.expanduser(os.environ.get("CHARLIE_HOME", "~/.charlie"))
CONFIG_PATH = os.path.join(CHARLIE_HOME, "config.json")
MEMORY_PATH = os.path.join(CHARLIE_HOME, "memory.md")
SESSIONS_DIR = os.path.join(CHARLIE_HOME, "sessions")

DEFAULT_CONFIG = {
    "provider": "ollama",
    "temperature": 0.7,
    "max_tool_rounds": 12,
    "auto_approve_commands": False,
    "context_messages": 40,
    "providers": {
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key": "",
            "model": "qwen2.5:7b",
        },
        "lmstudio": {
            "base_url": "http://localhost:1234/v1",
            "api_key": "",
            "model": "local-model",
        },
        "llamacpp": {
            "base_url": "http://localhost:8080/v1",
            "api_key": "",
            "model": "default",
        },
        "vllm": {
            "base_url": "http://localhost:8000/v1",
            "api_key": "",
            "model": "default",
        },
        "localai": {
            "base_url": "http://localhost:8080/v1",
            "api_key": "",
            "model": "default",
        },
        "jan": {
            "base_url": "http://localhost:1337/v1",
            "api_key": "",
            "model": "default",
        },
        # Cloud provider — OFF by default. Charlie will warn you before using
        # any endpoint that is not on your own machine: cloud APIs cost money
        # and your prompts leave your computer.
        "grok": {
            "base_url": "https://api.x.ai/v1",
            "api_key": "",
            "model": "grok-3",
            "cloud": True,
        },
    },
}

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


def load_config():
    os.makedirs(CHARLIE_HOME, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            for key, val in user_cfg.items():
                if key == "providers" and isinstance(val, dict):
                    for pname, pconf in val.items():
                        cfg["providers"].setdefault(pname, {}).update(pconf)
                else:
                    cfg[key] = val
        except (ValueError, OSError) as exc:
            print(color(f"[config] Could not read {CONFIG_PATH}: {exc}. "
                        "Using defaults.", "yellow"))
    else:
        save_config(cfg)
    return cfg


def save_config(cfg):
    os.makedirs(CHARLIE_HOME, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def is_local_url(url):
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    return host.lower() in LOCAL_HOSTS


# --------------------------------------------------------------------------
# Terminal colors
# --------------------------------------------------------------------------

_COLORS = {
    "red": "31", "green": "32", "yellow": "33", "blue": "34",
    "magenta": "35", "cyan": "36", "gray": "90", "bold": "1", "dim": "2",
}
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def color(text, *names):
    if not _USE_COLOR:
        return text
    codes = ";".join(_COLORS[n] for n in names if n in _COLORS)
    return f"\033[{codes}m{text}\033[0m"


# --------------------------------------------------------------------------
# HTTP (stdlib only; bypass system proxies for local servers)
# --------------------------------------------------------------------------

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_DEFAULT_OPENER = urllib.request.build_opener()


def http_request(url, payload=None, headers=None, method=None, timeout=600):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json",
                   "User-Agent": f"Charlie/{VERSION}"}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=req_headers,
                                 method=method or ("POST" if data else "GET"))
    opener = _NO_PROXY_OPENER if is_local_url(url) else _DEFAULT_OPENER
    return opener.open(req, timeout=timeout)


# --------------------------------------------------------------------------
# Persistent local memory
# --------------------------------------------------------------------------

def load_memory():
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""
    return ""


def append_memory(note):
    os.makedirs(CHARLIE_HOME, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    with open(MEMORY_PATH, "a", encoding="utf-8") as f:
        f.write(f"- ({stamp}) {note.strip()}\n")


def clear_memory():
    if os.path.exists(MEMORY_PATH):
        os.remove(MEMORY_PATH)


# --------------------------------------------------------------------------
# Tools — Charlie's hands
# --------------------------------------------------------------------------

MAX_TOOL_OUTPUT = 12000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".cache", "dist", "build", ".next", "target"}


def _truncate(text, limit=MAX_TOOL_OUTPUT):
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated, {len(text)} chars total]"
    return text


def tool_read_file(path, offset=1, limit=400):
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Error: no such file: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        return f"Error reading {path}: {exc}"
    offset = max(1, int(offset or 1))
    limit = max(1, int(limit or 400))
    chunk = lines[offset - 1:offset - 1 + limit]
    numbered = "".join(f"{i}\t{line}" for i, line in
                       enumerate(chunk, start=offset))
    header = f"[{path} — lines {offset}-{offset + len(chunk) - 1} of {len(lines)}]\n"
    return _truncate(header + numbered)


def tool_write_file(path, content):
    path = os.path.expanduser(path)
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        return f"Error writing {path}: {exc}"
    print(color(f"  ✏  wrote {path} ({len(content)} chars)", "gray"))
    return f"Wrote {len(content)} chars to {path}"


def tool_edit_file(path, old_text, new_text):
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Error: no such file: {path}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        return f"Error reading {path}: {exc}"
    count = content.count(old_text)
    if count == 0:
        return "Error: old_text not found in file. Read the file first and copy the text exactly."
    if count > 1:
        return f"Error: old_text appears {count} times; include more surrounding context so it is unique."
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace(old_text, new_text, 1))
    print(color(f"  ✏  edited {path}", "gray"))
    return f"Edited {path}"


def tool_list_dir(path="."):
    path = os.path.expanduser(path or ".")
    if not os.path.isdir(path):
        return f"Error: no such directory: {path}"
    entries = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append(name + "/" if os.path.isdir(full) else name)
    except OSError as exc:
        return f"Error listing {path}: {exc}"
    return _truncate("\n".join(entries) or "(empty directory)")


def tool_search_files(pattern, path=".", file_glob=""):
    path = os.path.expanduser(path or ".")
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"Error: bad regex: {exc}"
    glob_rx = None
    if file_glob:
        glob_rx = re.compile(
            "^" + re.escape(file_glob).replace(r"\*", ".*").replace(r"\?", ".") + "$")
    hits, scanned = [], 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            if glob_rx and not glob_rx.match(fname):
                continue
            full = os.path.join(root, fname)
            scanned += 1
            if scanned > 5000 or len(hits) >= 100:
                break
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append(f"{full}:{lineno}: {line.rstrip()[:200]}")
                            if len(hits) >= 100:
                                break
            except OSError:
                continue
        if scanned > 5000 or len(hits) >= 100:
            break
    if not hits:
        return "No matches."
    return _truncate("\n".join(hits))


def tool_run_command(command, ctx):
    if not ctx["config"].get("auto_approve_commands") and not ctx.get("yolo"):
        print(color(f"\n  Charlie wants to run: ", "yellow") +
              color(command, "bold"))
        try:
            answer = input(color("  Allow? [y/N] ", "yellow")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            return "User declined to run this command."
    print(color(f"  $ {command}", "gray"))
    try:
        proc = subprocess.run(command, shell=True, capture_output=True,
                              text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 180 seconds."
    out = proc.stdout or ""
    err = proc.stderr or ""
    result = out
    if err:
        result += ("\n[stderr]\n" + err)
    result += f"\n[exit code: {proc.returncode}]"
    return _truncate(result.strip())


def tool_fetch_url(url, ctx):
    if not is_local_url(url):
        print(color(f"\n  Charlie wants to fetch: {url}", "yellow"))
        print(color("  (this request leaves your machine)", "dim"))
        if not ctx.get("yolo"):
            try:
                answer = input(color("  Allow? [y/N] ", "yellow")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "n"
            if answer not in ("y", "yes"):
                return "User declined the network request."
    try:
        with http_request(url, timeout=30) as resp:
            body = resp.read(500_000).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 — report any fetch failure to the model
        return f"Error fetching {url}: {exc}"
    # crude HTML → text
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n\n", body)
    return _truncate(body.strip(), 8000)


def tool_remember(note):
    append_memory(note)
    print(color(f"  🧠 remembered: {note.strip()[:80]}", "gray"))
    return "Saved to long-term memory."


TOOLS = [
    {
        "name": "read_file",
        "description": "Read a text file (returns numbered lines). Use offset/limit for large files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "offset": {"type": "integer", "description": "1-based first line (default 1)"},
                "limit": {"type": "integer", "description": "Max lines to return (default 400)"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace one exact occurrence of old_text with new_text in a file. old_text must match exactly and be unique.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the contents of a directory.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory (default '.')"}},
        },
    },
    {
        "name": "search_files",
        "description": "Search file contents recursively with a regex. Optionally filter filenames with a glob like *.py.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression"},
                "path": {"type": "string", "description": "Root directory (default '.')"},
                "file_glob": {"type": "string", "description": "Filename filter, e.g. *.py"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command on the user's machine and return its output. The user is asked for permission first.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "fetch_url",
        "description": "Fetch a web page or API URL and return its text. The user is asked for permission for non-local URLs.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "remember",
        "description": "Save a short fact about the user or their preferences to Charlie's permanent local memory.",
        "parameters": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
]


def execute_tool(name, args, ctx):
    try:
        if name == "read_file":
            return tool_read_file(args.get("path", ""), args.get("offset", 1),
                                  args.get("limit", 400))
        if name == "write_file":
            return tool_write_file(args.get("path", ""), args.get("content", ""))
        if name == "edit_file":
            return tool_edit_file(args.get("path", ""), args.get("old_text", ""),
                                  args.get("new_text", ""))
        if name == "list_dir":
            return tool_list_dir(args.get("path", "."))
        if name == "search_files":
            return tool_search_files(args.get("pattern", ""), args.get("path", "."),
                                     args.get("file_glob", ""))
        if name == "run_command":
            return tool_run_command(args.get("command", ""), ctx)
        if name == "fetch_url":
            return tool_fetch_url(args.get("url", ""), ctx)
        if name == "remember":
            return tool_remember(args.get("note", ""))
        return f"Error: unknown tool '{name}'"
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
        return f"Error in tool {name}: {exc}"


def openai_tool_spec():
    return [{"type": "function", "function": t} for t in TOOLS]


# --------------------------------------------------------------------------
# Charlie's persona
# --------------------------------------------------------------------------

def system_prompt(ctx):
    memory = load_memory()
    memory_block = f"\n\nThings you remember about the user:\n{memory}" if memory else ""
    tool_note = ""
    if not ctx.get("native_tools", True):
        tool_note = TEXT_TOOL_PROTOCOL
    return f"""You are Charlie, a standalone AI assistant who lives entirely on the user's own computer. You use she/her pronouns. You are warm, sharp, direct, and occasionally playful — a capable engineer's assistant, not a corporate chatbot.

Core facts about yourself:
- You run 100% locally. You are not connected to any company, platform, or paid service. You never charge money and you never send the user's data anywhere.
- Your brain is an open-source language model served by {ctx['provider_name']} on this machine.
- Everything you know about the user is stored in a plain text file in ~/.charlie/ that they can read or delete at any time.

How you work:
- You have tools: reading/writing/editing files, searching code, listing directories, running shell commands (with the user's permission), fetching URLs, and saving memories. Use them proactively when they would help — do not guess about files or system state you can check.
- Working directory: {os.getcwd()}
- Today's date: {datetime.date.today().isoformat()}
- When asked to do multi-step work, keep using tools until the job is done, then summarize what you did.
- Be concise. Answer simple questions in a sentence or two. Never pad.
- When you learn a lasting fact about the user (their name, preferences, projects), use the remember tool.{tool_note}{memory_block}"""


TEXT_TOOL_PROTOCOL = """

TOOL CALLS (text protocol): your model backend does not support native tool calling, so to use a tool, reply with ONLY a fenced block like:
```tool
{"name": "read_file", "arguments": {"path": "notes.txt"}}
```
One tool call per reply. The result will come back as the next user message prefixed with [tool result]. When you have everything you need, reply normally with no tool block.

Available tools:
""" + "\n".join(
    f"- {t['name']}: {t['description']} Arguments: "
    + ", ".join(t["parameters"].get("properties", {}).keys())
    for t in TOOLS
)


# --------------------------------------------------------------------------
# Chat backend (OpenAI-compatible /v1/chat/completions, streaming)
# --------------------------------------------------------------------------

class ChatError(Exception):
    pass


def stream_chat(ctx, messages, use_tools):
    """Stream one assistant turn. Returns (content, tool_calls)."""
    prov = ctx["provider"]
    payload = {
        "model": prov["model"],
        "messages": messages,
        "temperature": ctx["config"].get("temperature", 0.7),
        "stream": True,
    }
    if use_tools:
        payload["tools"] = openai_tool_spec()
    headers = {}
    if prov.get("api_key"):
        headers["Authorization"] = "Bearer " + prov["api_key"]
    url = prov["base_url"].rstrip("/") + "/chat/completions"

    try:
        resp = http_request(url, payload, headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:2000]
        raise ChatError(f"HTTP {exc.code} from {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ChatError(f"Cannot reach {url}: {exc.reason}") from exc

    content_parts = []
    tool_calls = {}  # index -> {id, name, arguments}
    printed_prefix = False
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                if not printed_prefix:
                    sys.stdout.write(color("Charlie ▸ ", "magenta", "bold"))
                    printed_prefix = True
                sys.stdout.write(piece)
                sys.stdout.flush()
                content_parts.append(piece)
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = tool_calls.setdefault(
                    idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    if printed_prefix:
        sys.stdout.write("\n")
        sys.stdout.flush()
    calls = [tool_calls[i] for i in sorted(tool_calls)]
    return "".join(content_parts), calls


TEXT_TOOL_RE = re.compile(r"```tool\s*\n(.*?)```", re.DOTALL)


def parse_text_tool_call(content):
    match = TEXT_TOOL_RE.search(content or "")
    if not match:
        return None
    try:
        obj = json.loads(match.group(1).strip())
        if isinstance(obj, dict) and obj.get("name"):
            return obj
    except ValueError:
        pass
    return None


def run_turn(ctx, messages):
    """Run one full agent turn: model -> tools -> model ... -> final answer."""
    max_rounds = ctx["config"].get("max_tool_rounds", 12)
    for _round in range(max_rounds):
        use_native = ctx.get("native_tools", True)
        try:
            content, calls = stream_chat(ctx, messages, use_tools=use_native)
        except ChatError as exc:
            # Some servers reject the `tools` field — fall back to the
            # text protocol and retry once.
            if use_native and ("tool" in str(exc).lower() or "400" in str(exc)):
                ctx["native_tools"] = False
                messages[0] = {"role": "system", "content": system_prompt(ctx)}
                print(color("  (backend lacks native tool support — "
                            "switching to text protocol)", "dim"))
                continue
            raise

        if use_native and calls:
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {"id": c["id"] or f"call_{i}", "type": "function",
                     "function": {"name": c["name"], "arguments": c["arguments"]}}
                    for i, c in enumerate(calls)
                ],
            }
            messages.append(assistant_msg)
            for i, call in enumerate(calls):
                try:
                    args = json.loads(call["arguments"] or "{}")
                except ValueError:
                    args = {}
                print(color(f"  ⚙ {call['name']}"
                            f"({json.dumps(args)[:160]})", "cyan"))
                result = execute_tool(call["name"], args, ctx)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"] or f"call_{i}",
                    "content": result,
                })
            continue

        if not use_native:
            text_call = parse_text_tool_call(content)
            if text_call:
                messages.append({"role": "assistant", "content": content})
                args = text_call.get("arguments") or {}
                print(color(f"  ⚙ {text_call['name']}"
                            f"({json.dumps(args)[:160]})", "cyan"))
                result = execute_tool(text_call["name"], args, ctx)
                messages.append({"role": "user",
                                 "content": f"[tool result]\n{result}"})
                continue

        messages.append({"role": "assistant", "content": content})
        return content
    print(color("  (stopped: reached max tool rounds)", "yellow"))
    return ""


# --------------------------------------------------------------------------
# Provider helpers
# --------------------------------------------------------------------------

def ollama_available_models(base_url):
    """Best effort: list models from Ollama's native API."""
    root = base_url.rsplit("/v1", 1)[0]
    try:
        with http_request(root + "/api/tags", timeout=5) as resp:
            data = json.load(resp)
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:  # noqa: BLE001 — model listing is optional
        return None


def check_provider(ctx):
    """Verify the backend is reachable; help the user if not."""
    prov = ctx["provider"]
    name = ctx["provider_name"]
    if prov.get("cloud") or not is_local_url(prov["base_url"]):
        print(color("  ⚠ WARNING: provider '%s' is NOT on this machine "
                    "(%s)." % (name, prov["base_url"]), "yellow"))
        print(color("    Your prompts will leave your computer and the "
                    "service may charge you.", "yellow"))
        if not prov.get("api_key"):
            print(color("    No API key configured for it either — "
                        "switch back with: /provider ollama", "yellow"))
        return

    if name == "ollama" or "11434" in prov["base_url"]:
        models = ollama_available_models(prov["base_url"])
        if models is None:
            print(color("  ✗ Cannot reach Ollama at "
                        f"{prov['base_url']}.", "red"))
            print(color("    Install it (free, open source): "
                        "https://ollama.com/download", "dim"))
            print(color("    Then run:  ollama pull " + prov["model"], "dim"))
            return
        if not models:
            print(color("  ✗ Ollama is running but has no models yet.", "red"))
            print(color(f"    Run:  ollama pull {prov['model']}", "dim"))
            return
        if prov["model"] not in models:
            base_names = {m.split(":")[0] for m in models}
            if prov["model"].split(":")[0] not in base_names:
                fallback = models[0]
                print(color(f"  model '{prov['model']}' not found; "
                            f"using '{fallback}'", "yellow"))
                print(color("    (change any time with /model <name>; "
                            f"installed: {', '.join(models)})", "dim"))
                prov["model"] = fallback
        print(color(f"  ✓ Ollama ready — model: {prov['model']}", "green"))
    else:
        print(color(f"  provider: {name} @ {prov['base_url']} "
                    f"(model: {prov['model']})", "dim"))


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

def save_session(messages):
    if len(messages) <= 1:
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(SESSIONS_DIR, f"session-{stamp}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2)
        return path
    except OSError:
        return None


def trim_context(ctx, messages):
    """Keep the system prompt plus the most recent N messages."""
    keep = ctx["config"].get("context_messages", 40)
    if len(messages) > keep + 1:
        head, tail = messages[:1], messages[-(keep):]
        # never start the tail on a dangling tool result
        while tail and tail[0].get("role") == "tool":
            tail = tail[1:]
        messages[:] = head + tail


# --------------------------------------------------------------------------
# REPL
# --------------------------------------------------------------------------

BANNER = r"""
   ____ _                _ _
  / ___| |__   __ _ _ __| (_) ___
 | |   | '_ \ / _` | '__| | |/ _ \
 | |___| | | | (_| | |  | | |  __/
  \____|_| |_|\__,_|_|  |_|_|\___|
"""

HELP = """
Commands:
  /help                 show this help
  /model [name]         show or switch the model on the current provider
  /models               list models installed in Ollama
  /provider [name]      show or switch provider (ollama, lmstudio, llamacpp,
                        vllm, localai, jan, grok, ...)
  /providers            list configured providers
  /memory               show Charlie's long-term memory
  /forget               erase Charlie's long-term memory
  /clear                start a fresh conversation
  /yolo                 toggle auto-approval of shell commands (this session)
  /config               show the config file location and contents
  /save                 save this conversation to ~/.charlie/sessions/
  /exit                 leave (also Ctrl-D)

Anything else you type goes straight to Charlie.
"""


def make_ctx(cfg):
    pname = cfg.get("provider", "ollama")
    if pname not in cfg["providers"]:
        print(color(f"[config] unknown provider '{pname}', using ollama", "yellow"))
        pname = "ollama"
    return {
        "config": cfg,
        "provider_name": pname,
        "provider": cfg["providers"][pname],
        "native_tools": True,
        "yolo": False,
    }


def handle_command(cmd, ctx, messages):
    """Returns True if the REPL should exit."""
    cfg = ctx["config"]
    parts = cmd.split(None, 1)
    name = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if name in ("/exit", "/quit", "/q"):
        return True
    if name == "/help":
        print(HELP)
    elif name == "/clear":
        del messages[1:]
        messages[0] = {"role": "system", "content": system_prompt(ctx)}
        print(color("  conversation cleared", "gray"))
    elif name == "/model":
        if arg:
            ctx["provider"]["model"] = arg
            save_config(cfg)
            print(color(f"  model set to {arg}", "green"))
        else:
            print(f"  current model: {ctx['provider']['model']}")
    elif name == "/models":
        models = ollama_available_models(
            cfg["providers"]["ollama"]["base_url"])
        if models:
            print("  installed in Ollama:\n    " + "\n    ".join(models))
        else:
            print(color("  couldn't list models (is Ollama running?)", "yellow"))
    elif name == "/provider":
        if not arg:
            print(f"  current provider: {ctx['provider_name']} "
                  f"@ {ctx['provider']['base_url']}")
        elif arg in cfg["providers"]:
            cfg["provider"] = arg
            ctx["provider_name"] = arg
            ctx["provider"] = cfg["providers"][arg]
            ctx["native_tools"] = True
            save_config(cfg)
            check_provider(ctx)
            messages[0] = {"role": "system", "content": system_prompt(ctx)}
        else:
            print(color(f"  unknown provider '{arg}' — see /providers", "yellow"))
    elif name == "/providers":
        for pname, pconf in cfg["providers"].items():
            marker = "▸" if pname == ctx["provider_name"] else " "
            where = "" if is_local_url(pconf["base_url"]) else color("  [CLOUD — costs money, data leaves your machine]", "yellow")
            print(f"  {marker} {pname:10s} {pconf['base_url']}  "
                  f"(model: {pconf.get('model', '?')}){where}")
    elif name == "/memory":
        mem = load_memory()
        print(mem if mem else color("  (no memories yet)", "gray"))
    elif name == "/forget":
        clear_memory()
        print(color("  memory erased", "gray"))
    elif name == "/yolo":
        ctx["yolo"] = not ctx["yolo"]
        state = "ON — commands run without asking" if ctx["yolo"] else "off"
        print(color(f"  yolo mode {state}", "yellow"))
    elif name == "/config":
        print(f"  config file: {CONFIG_PATH}")
        print(textwrap.indent(json.dumps(cfg, indent=2), "  "))
    elif name == "/save":
        path = save_session(messages)
        print(color(f"  saved to {path}" if path else "  nothing to save", "gray"))
    else:
        print(color(f"  unknown command {name} — try /help", "yellow"))
    return False


def repl(ctx, one_shot=None):
    messages = [{"role": "system", "content": system_prompt(ctx)}]

    if one_shot:
        messages.append({"role": "user", "content": one_shot})
        try:
            run_turn(ctx, messages)
        except ChatError as exc:
            print(color(f"  ✗ {exc}", "red"))
            return 1
        return 0

    print(color(BANNER, "magenta"))
    print(color(f"  Charlie v{VERSION} — your standalone, local AI. "
                "No cloud. No fees. No spying.", "bold"))
    print(color("  type /help for commands, Ctrl-D to leave\n", "dim"))
    check_provider(ctx)
    print()

    while True:
        try:
            user_input = input(color("You ▸ ", "green", "bold")).strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue
        if not user_input:
            continue
        if user_input.startswith("/"):
            if handle_command(user_input, ctx, messages):
                break
            continue

        messages.append({"role": "user", "content": user_input})
        trim_context(ctx, messages)
        try:
            run_turn(ctx, messages)
        except ChatError as exc:
            print(color(f"  ✗ {exc}", "red"))
            messages.pop()  # let the user retry cleanly
        except KeyboardInterrupt:
            print(color("\n  (interrupted)", "dim"))
        print()

    path = save_session(messages)
    if path:
        print(color(f"  session saved: {path}", "dim"))
    print(color("  Charlie ▸ bye — I'll be right here when you need me.",
                "magenta"))
    return 0


def main():
    signal.signal(signal.SIGINT, signal.default_int_handler)
    cfg = load_config()
    ctx = make_ctx(cfg)
    one_shot = " ".join(sys.argv[1:]).strip() or None
    if one_shot in ("-h", "--help"):
        print(__doc__)
        print(HELP)
        return 0
    if one_shot in ("-v", "--version"):
        print(f"Charlie {VERSION}")
        return 0
    return repl(ctx, one_shot)


if __name__ == "__main__":
    sys.exit(main())
