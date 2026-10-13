"""Tool definitions (OpenAI/Ollama format) and dispatch."""
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

from hub.tools import file_system, web_search, shell, clipboard, system_info, notifications, timers, window_control
from hub import memory

def _fn(name: str, description: str, parameters: dict) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}

TOOL_DEFINITIONS = [
    _fn("file_read", "Read the contents of a file on the hub machine.", {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to FILE_SYSTEM_ROOT"},
        },
        "required": ["path"],
    }),
    _fn("file_write", "Write content to a file on the hub machine. Creates parent directories as needed.", {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to FILE_SYSTEM_ROOT"},
            "content": {"type": "string", "description": "Text content to write"},
        },
        "required": ["path", "content"],
    }),
    _fn("file_list", "List the contents of a directory on the hub machine.", {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path relative to FILE_SYSTEM_ROOT (empty = root)"},
        },
        "required": [],
    }),
    _fn("web_search", "Search the web using Tavily. Returns titles, URLs, and snippets.", {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Maximum results to return (default 5)"},
        },
        "required": ["query"],
    }),
    _fn("memory_write", "Save a fact to IRIS's world model. Use for new information worth remembering long-term.", {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact to store"},
            "tier": {
                "type": "string",
                "enum": ["core", "relevant", "archive"],
                "description": "core = always injected; relevant = fetched per query; archive = searchable only",
            },
            "importance": {"type": "number", "description": "0.0-1.0 importance score"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional topic tags"},
        },
        "required": ["content"],
    }),
    _fn("memory_recall", "Search IRIS's world model for facts matching a query.", {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords to search for"},
            "limit": {"type": "integer", "description": "Max facts to return (default 10)"},
        },
        "required": ["query"],
    }),
    _fn("shell_run", "Execute a shell command with output capture. Refuses obviously destructive patterns.", {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Max execution time in seconds (default 30, max 30)"},
        },
        "required": ["command"],
    }),
    _fn("clipboard_read", "Read the system clipboard.", {
        "type": "object",
        "properties": {},
        "required": [],
    }),
    _fn("clipboard_write", "Write text to the system clipboard.", {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to copy to clipboard"},
        },
        "required": ["text"],
    }),
    _fn("system_info", "Get system information: CPU, RAM, disk, battery, hostname, OS.", {
        "type": "object",
        "properties": {},
        "required": [],
    }),
    _fn("notify", "Send a desktop notification.", {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Notification title"},
            "message": {"type": "string", "description": "Notification message"},
        },
        "required": ["title", "message"],
    }),
    _fn("timer_set", "Set a timer that fires and sends a WebSocket notification.", {
        "type": "object",
        "properties": {
            "seconds": {"type": "integer", "description": "Duration in seconds"},
            "message": {"type": "string", "description": "Message to send when timer fires"},
        },
        "required": ["seconds", "message"],
    }),
    _fn("window_list", "List all open windows on the system.", {
        "type": "object",
        "properties": {},
        "required": [],
    }),
    _fn("window_focus", "Focus a window by title (partial match).", {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Window title to search for"},
        },
        "required": ["title"],
    }),
    _fn("app_open", "Open an application by name or path.", {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Application name or path (e.g., 'notepad', 'C:\\Program Files\\App\\app.exe')"},
        },
        "required": ["name"],
    }),
]


def dispatch(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return a JSON string result (sync dispatch)."""
    try:
        if tool_name == "file_read":
            result = file_system.read_file(tool_input["path"])
        elif tool_name == "file_write":
            result = file_system.write_file(tool_input["path"], tool_input["content"])
        elif tool_name == "file_list":
            result = file_system.list_directory(tool_input.get("path", ""))
        elif tool_name == "web_search":
            result = web_search.search(tool_input["query"], tool_input.get("max_results", 5))
        elif tool_name == "memory_write":
            fact_id = memory.write_fact(
                content=tool_input["content"],
                tier=tool_input.get("tier", "relevant"),
                importance=tool_input.get("importance", 0.5),
                tags=tool_input.get("tags"),
            )
            result = {"ok": True, "id": fact_id}
        elif tool_name == "memory_recall":
            facts = memory.search_facts(tool_input["query"], tool_input.get("limit", 10))
            result = {"ok": True, "facts": facts}
        elif tool_name == "shell_run":
            result = shell.run_command(
                tool_input["command"],
                tool_input.get("timeout", 30),
            )
        elif tool_name == "clipboard_read":
            result = clipboard.read_clipboard()
        elif tool_name == "clipboard_write":
            result = clipboard.write_clipboard(tool_input["text"])
        elif tool_name == "system_info":
            result = system_info.get_system_info()
        elif tool_name == "notify":
            result = notifications.send_notification(
                tool_input["title"],
                tool_input["message"],
            )
        elif tool_name == "timer_set":
            result = timers.set_timer(
                tool_input["seconds"],
                tool_input["message"],
            )
        elif tool_name == "window_list":
            result = window_control.list_windows()
        elif tool_name == "window_focus":
            result = window_control.focus_window(tool_input["title"])
        elif tool_name == "app_open":
            result = window_control.open_app(tool_input["name"])
        else:
            result = {"ok": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    return json.dumps(result)


async def async_dispatch(tool_name: str, tool_input: dict, ws: "WebSocket") -> str:
    """
    Execute a tool and return a JSON string result (async dispatch).
    Handles tools that need async/WebSocket context.
    """
    try:
        if tool_name == "timer_set":
            # Spawn the async timer task
            import asyncio
            seconds = tool_input["seconds"]
            message = tool_input["message"]
            asyncio.create_task(timers.set_timer_task(seconds, message, ws))
            result = timers.set_timer(seconds, message)
        else:
            # Delegate to sync dispatch for all other tools
            result_json = dispatch(tool_name, tool_input)
            result = json.loads(result_json)
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    return json.dumps(result)
