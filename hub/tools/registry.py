"""Tool definitions (OpenAI/Ollama format) and dispatch."""
import json
from hub.tools import file_system, web_search
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
]


def dispatch(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return a JSON string result."""
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
        else:
            result = {"ok": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"ok": False, "error": str(e)}

    return json.dumps(result)
