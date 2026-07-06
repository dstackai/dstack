# claude-agent-sdk

## Summary
Comparison of Claude Agent SDK (Python) vs. plain anthropic SDK for embedding an autonomous deployment agent in dstack. **Recommend Agent SDK (v0.2.110, Python 3.10+) for first implementation**: it bundles the Claude Code CLI binary (not Node.js), provides built-in autonomous tool execution with permission control modes, handles the agentic loop automatically, and supports skills loading convention. The plain anthropic SDK (v0.116.0, Python 3.9+) is lighter-weight but requires manual tool-loop implementation. Both authenticate via ANTHROPIC_API_KEY. Agent SDK deployment footprint: bundled binary CLI + Python runtime ~300MB per platform. Defer plain SDK approach until Agent SDK proves insufficient for the autonomous deployment use case.

## Key files
- claude-agent-sdk (PyPI: pip install claude-agent-sdk) — query(), ClaudeSDKClient, ClaudeAgentOptions, @tool, create_sdk_mcp_server(), HookMatcher, AgentDefinition, AsyncAnthropic pattern — Official Python Agent SDK. Version 0.2.110 released June 24, 2026. Requires Python 3.10+. Bundles Claude Code CLI binary (not Node.js; packed as platform-specific wheels for macOS ARM64/x86-64, Linux, Windows). GitHub: anthropics/claude-agent-sdk-python. Bundling mechanism: CLI is included in wheel distribution; used by default via stdio; custom path override supported via ClaudeAgentOptions(cli_path=...).
- anthropic (PyPI: pip install anthropic) — Anthropic, AsyncAnthropic, messages.create(), messages.stream(), @beta_tool, tool_runner, messages.count_tokens(), messages.batches, ToolUseBlock, ToolResultBlock — Official Anthropic Python SDK. Version 0.116.0 released July 2, 2026. Requires Python 3.9+. Pure Python, no external binaries. GitHub: anthropics/anthropic-sdk-python. Includes optional extras: [bedrock], [vertex], [aws] for cloud integrations; [aiohttp] for better async concurrency.
- https://code.claude.com/docs/en/agent-sdk/overview — Built-in tools, hook callbacks, permission_mode values, mcp_servers dict config, agents dict, allowed_tools/disallowed_tools lists — Official Agent SDK documentation. Covers query()/ClaudeSDKClient interfaces, built-in tools (Read, Write, Edit, Bash, Monitor, Glob, Grep, WebSearch, WebFetch, AskUserQuestion), hooks lifecycle (PreToolUse, PostToolUse, Stop, SessionStart, SessionEnd, UserPromptSubmit), subagents, MCP integration, permission model, sessions with resume(). Skills convention documented: .claude/skills/*/SKILL.md auto-loaded from working directory and ~/.claude/.

## Details
## A) Claude Agent SDK (Python)

### Package & Installation
- **Name**: `claude-agent-sdk`
- **Version**: 0.2.110 (June 24, 2026)
- **Python**: 3.10+
- **Installation**: `pip install claude-agent-sdk`
- **Bundling**: Bundles Claude Code CLI **as a binary** (not Node.js). Platform-specific wheels (macOS ARM64/x86-64, Linux, Windows). No separate Node.js installation or subprocess complexity.

### Core APIs

**Simple interface:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Deploy model X as dstack service",
    options=ClaudeAgentOptions(allowed_tools=["Bash", "Read", "Write"])
):
    print(message)
```

**Interactive sessions:**
```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt)
    async for msg in client.receive_response():
        print(msg)
```

### Custom Tool Definition
Via `@tool` decorator + in-process MCP server (no subprocess overhead):
```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("verify_endpoint", "Verify endpoint reachability", {"url": str})
async def verify_endpoint(args):
    # Direct Python execution
    return {"content": [{"type": "text", "text": f"OK: {args['url']}"}]}

server = create_sdk_mcp_server(
    name="dstack-tools",
    version="1.0.0",
    tools=[verify_endpoint]
)

options = ClaudeAgentOptions(
    mcp_servers={"tools": server},
    allowed_tools=["mcp__tools__verify_endpoint"]  # Pre-approve
)
```

### Built-In Tools (Pre-Integrated)
Read, Write, Edit, Bash, Monitor, Glob, Grep, WebSearch, WebFetch, AskUserQuestion. All available without configuration.

### Permission Model (for Autonomous Headless Operation)
```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash"],      # Auto-approve list
    disallowed_tools=["DangerousTool"],           # Block list
    permission_mode='acceptEdits'                  # Auto-accept file edits
)
```
Evaluation order: `allowed_tools` → `disallowed_tools` → `permission_mode` fallback. No interactive approval prompts when tools pre-approved. **Can run fully autonomous in headless Docker environment.**

### Hooks (for Observability & Control)
```python
async def log_exec(input_data, tool_use_id, context):
    action = input_data.get("tool_input", {})
    audit_log.write(f"{tool_use_id}: {action}\n")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PostToolUse": [
            HookMatcher(matcher="Bash", hooks=[log_exec])
        ]
    }
)
```

### Authentication & Model Selection
- **API Key**: `ANTHROPIC_API_KEY` environment variable (standard)
- **Models**: Supports Claude Opus 4.8, Sonnet 4.6, Haiku 4.5, Fable 5 (June 2026 launch), Mythos 5 (trusted access)
- **Model config**: Set via options or defaults to latest available

### Skills Loading
SDK supports `.claude/` filesystem convention:
- `.claude/skills/*/SKILL.md` – Auto-loaded skill definitions
- `.claude/CLAUDE.md` – Project memory/context
- `setting_sources` parameter to restrict which sources load

**Not explicitly documented**: whether SDK has programmatic API to load skills from custom directories (e.g., `setting_sources` list-based config). This may require filesystem symlinks or copying skills into `.claude/`.

### Sessions & Context Persistence
```python
# Capture session ID on init
session_id = message.data["session_id"]

# Resume later with full context
async for msg in query(prompt="...", options=ClaudeAgentOptions(resume=session_id)):
    ...
```

### Deployment Footprint
- **Per-platform binary**: ~100–150 MB (CLI binary alone)
- **SDK library**: ~50 MB
- **Python runtime**: depends on container base
- **No Node.js required**: Binary CLI, not JavaScript runtime
- **Subprocess management**: Minimal; SDK handles stdio communication with bundled binary
- **Concurrent sessions**: Each async query spawns a CLI process; manage concurrency via asyncio limits

## B) Plain anthropic Python SDK

### Package & Installation
- **Name**: `anthropic`
- **Version**: 0.116.0 (July 2, 2026)
- **Python**: 3.9+
- **Installation**: `pip install anthropic`
- **Size**: ~10 MB, pure Python

### Core API (Manual Tool-Use Loop)

```python
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

messages = [{"role": "user", "content": "Deploy model X"}]
tools = [{"name": "bash", "description": "...", "input_schema": {...}}]

while True:
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        tools=tools,
        messages=messages
    )
    
    if response.stop_reason == "tool_use":
        # Manual loop: find tool calls, execute, collect results
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    }]
                })
                break
    else:
        break  # stop_reason == "end_turn"

print(response.content[-1].text)
```

### Tool Definition (Helper Decorator)
```python
from anthropic import beta_tool

@beta_tool
def bash_exec(command: str) -> str:
    """Execute bash command. Args: command (str): bash to run"""
    return subprocess.check_output(command, shell=True, text=True)

@beta_tool
def verify_endpoint(url: str) -> str:
    """Verify endpoint. Args: url (str): endpoint URL"""
    import requests
    return "OK" if requests.head(url).ok else "FAIL"
```

The `@beta_tool` decorator auto-generates the tool schema from function signature and docstring. **No built-in permission control**; you control tool availability by including/excluding from the `tools` list.

### Tool Runner Helper (Simplifies Loop)
```python
from anthropic import beta_tool

runner = client.beta.messages.tool_runner(
    model="claude-opus-4-8",
    max_tokens=4096,
    tools=[bash_exec, verify_endpoint],
    messages=[{"role": "user", "content": "Deploy model X"}]
)

for message in runner:
    if hasattr(message, "content"):
        print(message.content)
```
Still requires you to implement tool execution; the runner just collects the loop boilerplate. **Not equivalent to Agent SDK's autonomous execution.**

### Streaming
```python
with client.messages.stream(
    model="claude-opus-4-8",
    max_tokens=4096,
    tools=tools,
    messages=messages
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    final = stream.get_final_message()
```

### Web Search & Web Fetch Tools
Both available as built-in tools (since April 2026):
- `web_search_20260318` (dynamic filtering variant) – $10 per 1,000 searches + standard token costs
- `web_fetch_20250305` – Included in standard requests
Models supporting web tools: Opus 4.7+, Sonnet 4.6+, Opus 4.6+, Opus 4.5+, Haiku 4.5+, Sonnet 4.5+

### Prompt Caching
```python
response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": "You are a deployment agent...",
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[...]
)
```
Cached input costs 90% less. Useful for long system prompts. Works across multiple requests within 5-minute window.

### Token Counting
```python
count = client.messages.count_tokens(
    model="claude-opus-4-8",
    messages=[{"role": "user", "content": "Hello"}],
    tools=tools
)
print(count.input_tokens, count.output_tokens)

# Post-request usage
response = client.messages.create(...)
print(response.usage.input_tokens, response.usage.output_tokens)
```

### Structured Outputs
```python
response = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=4096,
    messages=[...],
    structured_output={"schema": {...}, "strict": True}
)
# Returns validated JSON matching schema
```

### Authentication & Model Selection
- **API Key**: `ANTHROPIC_API_KEY` environment variable
- **Models**: Same lineup as Agent SDK (Opus 4.8, Sonnet 4.6, Haiku 4.5, Fable 5, Mythos 5)
- **Cloud provider integrations**: Bedrock, Vertex AI, Foundry, Claude Platform on AWS (via `AnthropicBedrock`, `AnthropicVertex`, etc.)

### Deployment Footprint
- **Pure Python**: ~10 MB + httpx dependency
- **No CLI binary**: No subprocess overhead
- **No Node.js**: No runtime bloat
- **Lightweight**: Ideal for resource-constrained containers

### Error Handling & Reliability
```python
from anthropic import APIConnectionError, RateLimitError, APITimeoutError

try:
    response = client.messages.create(...)
except RateLimitError:
    # Automatic retries (default 2x); configure with max_retries=N
    pass
except APITimeoutError:
    # Default 10-minute timeout; configure per-request or globally
    pass
```

---

## Comparison Table

| Feature | Agent SDK | Plain SDK |
|---------|-----------|-----------|
| **Package** | `claude-agent-sdk` 0.2.110 | `anthropic` 0.116.0 |
| **Python** | 3.10+ | 3.9+ |
| **Size** | ~300 MB (bundled binary CLI) | ~10 MB (pure Python) |
| **Node.js required** | No (binary CLI) | No |
| **Agentic loop** | Automatic (query/ClaudeSDKClient) | Manual (messages.create loop) |
| **Tool definition** | `@tool` + in-process MCP | `@beta_tool` decorator |
| **Permission control** | `allowed_tools`, `disallowed_tools`, `permission_mode` | None (list-based inclusion) |
| **Headless autonomous** | Yes (permission_mode='acceptEdits') | Requires manual implementation |
| **Built-in tools** | Read, Write, Edit, Bash, Monitor, Glob, Grep, WebSearch, WebFetch, AskUserQuestion | None (define custom or use tool schema) |
| **Streaming** | Automatic in query loop | Via messages.stream() |
| **Web search/fetch** | Included | Included (webSearch/webFetch tools, since Apr 2026) |
| **Prompt caching** | Not mentioned | Yes, cache_control parameter |
| **Structured outputs** | Not mentioned | Yes, structured_output parameter |
| **Token counting** | Pre-request via query context | messages.count_tokens() + response.usage |
| **Sessions** | Yes, resume=session_id | Manual message history management |
| **Skills loading** | `.claude/skills/*/SKILL.md` convention | N/A |
| **Hooks** | Pre/PostToolUse, SessionStart/End, UserPromptSubmit | N/A |
| **Deployment** | Subprocess (CLI binary via stdio) | In-process HTTP calls |
| **Concurrency** | asyncio-based, one CLI process per query | asyncio-based, HTTP connection pooling |

---

## Recommendation: START WITH AGENT SDK

### Rationale
1. **Autonomous operation**: `permission_mode='acceptEdits'` + `allowed_tools` = fully headless, no approval prompts. dstack agent runs in a Docker container without user interaction.
2. **Tool loop already solved**: Agent SDK handles the agentic loop internally. You write the objective ("deploy model X"), Agent SDK calls tools, parses responses, repeats until `stop_reason != "tool_use"`.
3. **Built-in tools**: Read, Write, Edit, Bash, WebSearch, WebFetch all pre-integrated; no schema boilerplate.
4. **Permission granularity**: Block dangerous tools, auto-approve safe ones—critical for production agents touching infra.
5. **Skills convention**: `.claude/skills/` can hold domain-specific prompt files (e.g., "dstack-deployment-best-practices.md") loaded automatically.
6. **Observability**: Hooks let you audit every tool call, useful for logging/compliance in a managed service.
7. **No Node.js surprise**: Binary CLI, not JavaScript; deployment burden is bundle size, not runtime complexity.

### Gotchas / Verification Needed
- **Skill directory loading**: Documentation shows `.claude/skills/*/SKILL.md` convention but does NOT explicitly document programmatic API to point SDK at custom skill directories. May require filesystem setup or `setting_sources` config (not yet verified in official docs).
- **Prompt caching**: Agent SDK docs don't mention cache_control support; unclear if long system prompts benefit from caching. **May need to implement separately via custom MCP server or plain SDK for cost control on repeated deployments.**
- **Concurrent agents**: Each query spawns a CLI subprocess. In a multi-tenant dstack setup, concurrency management (asyncio semaphores) is on you.
- **Model selection**: Agent SDK supports model choice but default strategy unclear. Recommend explicit model selection for cost control (Haiku 4.5 for fast tasks, Sonnet 4.6 for complex deployments).
- **Structured outputs**: Agent SDK doesn't mention structured_output schema support. If the agent must return a validated JSON deployment report, may need to parse text or use plain SDK.

### Suggested Implementation Pattern (dstack AgentService)

```python
from claude_agent_sdk import query, ClaudeAgentOptions

class ClaudeAgentService:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
    
    async def deploy(self, objective: str) -> dict:
        # Pre-approve safe tools for autonomous operation
        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Write", "Bash", "WebSearch"],
            disallowed_tools=["DeleteFile"],  # Custom safety rules
            permission_mode="acceptEdits",
            system_prompt=f"You are a dstack deployment agent. Objective: {objective}"
        )
        
        result_text = ""
        async for message in query(prompt=objective, options=options):
            if hasattr(message, "result"):
                result_text = message.result
        
        return {"success": True, "output": result_text}
```

### Defer to Plain SDK If
- Prompt caching becomes critical for cost (long system prompts on every deployment). Plain SDK's `cache_control` is explicit.
- Agent SDK's structured output support lags behind needs (plain SDK has `structured_output` parameter).
- Concurrent session management becomes a bottleneck (plain SDK's HTTP is more amenable to connection pooling).
- Custom tools become complex and in-process MCP not sufficient (plain SDK's tool schema is more flexible).

### Cost / Token Considerations
- **Agent SDK**: No additional overhead; standard Claude pricing (input/output tokens). CLI binary overhead is one-time disk, not per-request.
- **Plain SDK**: Same; adds prompt caching option (10% cost on cached input).
- **Web search**: Both support. $10 per 1,000 searches.
- **Batch processing**: Not available in Agent SDK (built on CLI); plain SDK offers `messages.batches` for 50% discount on bulk async requests (might matter for large dstack deployments).

### What to Implement First (Behind AgentService Abstraction)
1. Basic `deploy(objective: str) -> dict` method returning success + logs
2. Tool allowlist (Bash, Read, WebSearch) + blocklist (Delete, Exec)
3. Hook for audit logging of all tool calls
4. Error handling for API key missing (early catch)
5. Model selection flag (default Sonnet 4.6, option for Haiku 4.5 for speed)

Defer: prompt caching, structured output schema, skill directory custom paths, concurrent session management—validate Agent SDK meets MVP first.

## Gotchas
**Agent SDK:**
- CLI subprocess per query; no persistent connection pooling. Concurrency scales with asyncio but spawns new processes. In high-throughput scenarios (100+ concurrent deployments), process overhead may become visible.
- Skill directory loading documented as convention (`.claude/skills/*/SKILL.md`) but no explicit programmatic API to restrict sources or load from custom paths. May need filesystem manipulation to use custom skill directories in dstack.
- Prompt caching not mentioned in Agent SDK docs; if long system prompts are repeated per deployment, caching benefit may be missed. Plain SDK's `cache_control` is explicit.
- Structured outputs not mentioned; if deployment report must be guaranteed JSON schema, may need post-processing or custom tool returning JSON string.
- Model selection: Default behavior unclear. Recommend explicit model flag in options to control cost (Haiku 4.5 for fast, Sonnet 4.6 for complex).
- Permission modes work but are SDK-level. If dstack needs finer-grained control (e.g., Bash only in specific directories), hook-based filtering required.

**Plain SDK:**
- Manual tool-use loop is boilerplate-heavy; easy to introduce bugs (forgetting to append assistant message, wrong tool_result format). Tool runner helper exists but does NOT automate loop—you still implement execution.
- No built-in permission model; must implement allowlist/blocklist at application layer.
- No native session resumption; message history is your responsibility.
- Skills concept doesn't exist; custom tools are pure Python functions or external MCP servers.
- Hooks don't exist; audit logging is manual.
- Lighter footprint but requires more application code to reach Agent SDK feature parity.

**Both:**
- API key via env var (standard); no option to pass key at init time (security best practice for 12-factor), though both support explicit client = Anthropic(api_key=...).
- No built-in support for multi-replica coordination (e.g., one deployment agent per dstack replica). Session IDs are local; cross-replica session sharing requires external persistence layer.
