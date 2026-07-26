"""Claude access for the runner: the Agent SDK over the owner's Claude Code
subscription login. NO API KEY EXISTS OR IS ACCEPTED — if the SDK or its
login is unavailable, callers get a RunnerLLMError and the intelligence job
is marked failed with the reason (the deterministic result stays live).
"""
import anyio


class RunnerLLMError(Exception):
    pass


def ask_claude(prompt: str, system: str = "", max_turns: int = 1) -> str:
    """One-shot text completion via the Claude Agent SDK (subscription auth)."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError as e:
        raise RunnerLLMError(f"claude-agent-sdk not installed: {e}")

    async def _run() -> str:
        chunks: list[str] = []
        options = ClaudeAgentOptions(
            system_prompt=system or None,
            max_turns=max_turns,
            allowed_tools=[],          # text-only: no tools, no side effects
        )
        async for message in query(prompt=prompt, options=options):
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
        return "\n".join(chunks).strip()

    try:
        return anyio.run(_run)
    except RunnerLLMError:
        raise
    except Exception as e:
        # transient SDK/CLI hiccups (seen in the wild: "returned an error
        # result: success") get exactly one retry before failing the pass
        import time
        time.sleep(5)
        try:
            return anyio.run(_run)
        except Exception:
            raise RunnerLLMError(f"Claude Agent SDK call failed: {e}")
