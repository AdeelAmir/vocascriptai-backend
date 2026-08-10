from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from typing import TypedDict
from app.services.GROQ_PROMPT import (
    get_summary_gen_prompt,
    prompt_plus_gen_merge,
    get_classification_prompt,
    get_prompt_for_type,
)
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

    # Fallback: auto-repair malformed JSON (handles smart quotes,
    # trailing commas, unescaped quotes, unterminated strings, etc.)
    try:
        repaired = repair_json(content)
        return json.loads(repaired)
    except Exception:
        pass

    # Last resort: brace-trimming (your original logic)
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


def classify_meeting(text: str, keys: list[str]) -> str:
    """Classify meeting type from first 750 words of transcript."""
    global CURRENT_KEY_INDEX

    # Use only first 700 words for classification
    first_750 = " ".join(text.split()[:750])

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            llm = get_llm(keys[key_index])
            result = llm.invoke([
                ("system", get_classification_prompt()),
                ("user", first_750)
            ])
            parse = safe_parse_json(result.content)
            meeting_type = parse.get("type", "general_discussion")
            print(f"[Classification] Meeting type detected: {meeting_type}")
            return meeting_type
        except Exception as e:
            result_obj = locals().get('result')
            result_content = getattr(result_obj, 'content', None)
            print(f"[DEBUG] Groq key {key_index+1} failed: {repr(e)}")
            print(f"[DEBUG] Groq response content: {repr(result_content)}")
            if is_rate_limit_error(e) or "empty response" in str(e).lower():
                backoff = 2 * (attempt + 1)
                print(f"[DEBUG] Backing off {backoff}s before trying next key please")
                time.sleep(backoff)
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            return "general_discussion"
    return "general_discussion"


class state_full(TypedDict):
    text: str
    summary_gen: str
    prompt_gen: list
    generate_prompt: bool
    generate_summary: bool
    keys: list[str]
    meeting_type: str  # ✅ add this


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


def summary_plus_prompt(state: state_full):
    global CURRENT_KEY_INDEX
    keys = state['keys']

    if state['generate_prompt'] == False:
        return {}

    # ✅ use pre-classified type from state instead of calling classify_meeting again
    meeting_type = state.get("meeting_type", "general_discussion")
    selected_prompt = get_prompt_for_type(meeting_type)

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            llm = get_llm(keys[key_index])
            result = llm.invoke([
                ("system", selected_prompt),
                ("user", state["text"])
            ])
            parse = safe_parse_json(result.content)
            CURRENT_KEY_INDEX = key_index
            return {"prompt_gen": parse.get("items", [])}
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

def merge_prompts(partial_prompts: list, keys: list[str], state: state_full) -> list:
    global CURRENT_KEY_INDEX

    if not partial_prompts:
        return []

    real_prompts = [p for p in partial_prompts if p.get("type") != "none"]
    if not real_prompts:
        return []

    input_text = json.dumps({"items": real_prompts}, indent=2)

    for attempt in range(len(keys)):
        key_index = (CURRENT_KEY_INDEX + attempt) % len(keys)
        try:
            llm = get_llm(keys[key_index])
            result = llm.invoke([
                ("system", prompt_plus_gen_merge()),
                ("user", input_text)
            ])
            parse = safe_parse_json(result.content)
            CURRENT_KEY_INDEX = key_index
            return parse.get("items", [])
        except Exception as e:
            result_obj = locals().get('result')
            result_content = getattr(result_obj, 'content', None)
            print(f"[DEBUG] Groq key {key_index+1} failed: {repr(e)}")
            print(f"[DEBUG] Groq response content: {repr(result_content)}")
            if is_rate_limit_error(e) or "empty response" in str(e).lower():
                backoff = 2 * (attempt + 1)
                print(f"[DEBUG] Backing off {backoff}s before trying next key")
                time.sleep(backoff)
                print(f"[Key {key_index + 1}] Rate limit or empty response, trying next key...")
                CURRENT_KEY_INDEX = (key_index + 1) % len(keys)
                continue
            raise

    raise Exception("All Groq API keys have reached their rate limits.")


def skip_node(state: state_full):
    return {}

def return_both(state: state_full):
    summary_result = summary_node(state)
    prompt_result = summary_plus_prompt(state)
    return {**summary_result, **prompt_result}

def route_after_summary(state: state_full):
    if state["generate_prompt"] == True and state["generate_summary"] == True:
        return "both"
    elif state["generate_prompt"] == True:
        return "summary_plus_prompt"
    elif state["generate_summary"] == True:
        return "summary_node"
    else:
        return 'skip'


graph = StateGraph(state_full)
graph.add_node("summary_node", summary_node)
graph.add_node("summary_plus_prompt", summary_plus_prompt)
graph.add_node("return_both", return_both)
graph.add_node("skip", skip_node)

graph.add_conditional_edges(START, route_after_summary, {
    "summary_plus_prompt": "summary_plus_prompt",
    "summary_node": "summary_node",
    "both": "return_both",
    "skip": "skip"
})

graph.add_edge("summary_plus_prompt", END)
graph.add_edge("summary_node", END)
graph.add_edge("return_both", END)
graph.add_edge("skip", END)

agent = graph.compile()