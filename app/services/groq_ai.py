from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from app.services.GROQ_PROMPT import get_summary_gen_prompt
from app.services.GEMINI_PROMPT import get_master_prompt
import json
import time
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.settings import Setting
from json_repair import repair_json
from app.core.encryption import decrypt

PLAIN_KEYS = ("MAX_FILE_SIZE_MB", "MAX_VIDEO_DURATION_MINUTES")

async def get_setting(key: str) -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if not setting:
            return None
        return setting.value if key in PLAIN_KEYS else decrypt(setting.value)


async def get_keys(prefix: str) -> list[str]:
    keys = []
    for i in range(1, 4):
        value = await get_setting(f"{prefix}_{i}")
        if value:
            keys.append(value)
    return keys

CURRENT_KEY_INDEX = 0


def is_rate_limit_error(e: Exception) -> bool:
    error_text = str(e).lower()
    return any(phrase in error_text for phrase in [
        "rate_limit_exceeded",
        "request too large",
        "tokens per minute",
        "rate limit",
    ])


def get_llm(api_key: str) -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        api_key=api_key,
    )


def safe_parse_json(content: str) -> dict:
    content = content.strip()
    if not content:
        raise Exception("Model returned empty response")
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    try:
        repaired = repair_json(content)
        return json.loads(repaired)
    except Exception:
        pass

    last_brace = content.rfind('}')
    first_brace = content.find('{')
    if last_brace != -1:
        try:
            return json.loads(content[:last_brace + 1])
        except json.JSONDecodeError:
            pass
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(content[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass
    raise Exception(f"Could not parse model response as JSON: {content[:200]}")


def generate_prompt_items(text: str, keys: list[str]) -> list[dict]:
    """Generate actionable prompts for the standard plan as well.

    Previously the Groq/standard path only generated a summary and always
    returned an empty prompt list.  That made prompt availability and count
    depend on the selected plan/provider rather than the transcript.
    """
    if not text or not keys:
        return []

    global CURRENT_KEY_INDEX
    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            llm = get_llm(keys[key_index])
            result = llm.invoke([
                ("system", get_master_prompt()),
                ("user", text),
            ])
            parsed = safe_parse_json(result.content)
            items = parsed.get("items", [])
            if not isinstance(items, list):
                return []
            CURRENT_KEY_INDEX = key_index
            return [item for item in items if isinstance(item, dict) and item.get("type") != "none"]
        except Exception as e:
            print(f"[DEBUG] Groq prompt generation key {key_index + 1} failed: {repr(e)}")
            if is_rate_limit_error(e) or "empty response" in str(e).lower():
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            raise

    raise Exception("All Groq API keys have reached their rate limits.")


class state_full(TypedDict):
    text: str
    summary_gen: str
    generate_summary: bool
    keys: list[str]


def summary_node(state: state_full):
    global CURRENT_KEY_INDEX
    keys = state['keys']

    if state['generate_summary'] == False:
        return {}

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            llm = get_llm(keys[key_index])
            result = llm.invoke([
                ("system", get_summary_gen_prompt()),
                ("user", state["text"])
            ])
            parse = safe_parse_json(result.content)
            CURRENT_KEY_INDEX = key_index
            return {"summary_gen": parse["summary"]}
        except Exception as e:
            result_obj = locals().get('result')
            result_content = getattr(result_obj, 'content', None)
            print(f"[DEBUG] Groq key {key_index+1} failed: {repr(e)}")
            print(f"[DEBUG] Groq response content: {repr(result_content)}")
            if is_rate_limit_error(e) or "empty response" in str(e).lower():
                backoff = 2 * (attempt + 1)
                print(f"[DEBUG] Backing off {backoff}s before trying next key")
                time.sleep(backoff)
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            raise

    raise Exception("All Groq API keys have reached their rate limits.")


def skip_node(state: state_full):
    return {}


def route(state: state_full):
    if state["generate_summary"] == True:
        return "summary_node"
    return "skip"


graph = StateGraph(state_full)
graph.add_node("summary_node", summary_node)
graph.add_node("skip", skip_node)

graph.add_conditional_edges(START, route, {
    "summary_node": "summary_node",
    "skip": "skip",
})

graph.add_edge("summary_node", END)
graph.add_edge("skip", END)

agent = graph.compile()
