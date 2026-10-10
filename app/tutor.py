"""The agentic tutor: Claude with tools, streaming sentence-by-sentence for low latency."""
import json
import os
import re
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from . import curriculum, store

client = AsyncAnthropic()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


@dataclass
class Session:
    level: str = "A1"
    mode: str = "lesson"
    stt: str = "auto"
    rate: str = "-15%"
    history: list = field(default_factory=list)
    drill_text: str | None = None
    turn: int = 0


TOOLS = [
    {
        "name": "add_vocab",
        "description": "Save new German words or phrases the learner just met, for spaced-repetition review later. Max 4 per call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "de": {"type": "string", "description": "German word or phrase, with article for nouns"},
                            "en": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["de", "en"],
                    },
                }
            },
            "required": ["items"],
        },
    },
    {
        "name": "get_review_items",
        "description": "Fetch vocabulary that is due for review now. Use at the start of a lesson and for quick warm-ups.",
        "input_schema": {"type": "object", "properties": {"n": {"type": "integer"}}},
    },
    {
        "name": "grade_review",
        "description": "Record how well the learner recalled a word during review. 0 = blackout, 3 = correct with effort, 5 = instant.",
        "input_schema": {
            "type": "object",
            "properties": {"de": {"type": "string"}, "quality": {"type": "integer"}},
            "required": ["de", "quality"],
        },
    },
    {
        "name": "request_pronunciation_drill",
        "description": "Start a scored pronunciation drill. Say the target German sentence aloud in your reply, ask the learner to repeat it, then the learner's NEXT utterance is scored word by word and the result arrives in a [pronunciation_result ...] line.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Short German sentence, 3 to 10 words"}},
            "required": ["text"],
        },
    },
    {
        "name": "update_progress",
        "description": "Save level, unit position and observations. Call when a unit is finished, when the learner clearly moves up a level, or at the end of a session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "enum": ["A1", "A2", "B1", "B2"]},
                "unit_index": {"type": "integer"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "record_exam_result",
        "description": "Save the estimated outcome of a mock Sprechen exam after you have given feedback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "string"},
                "estimated_score": {"type": "integer", "description": "0 to 100, where 60 is the pass mark"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "fixes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["level", "estimated_score"],
        },
    },
]


def run_tool(sess: Session, name: str, args: dict) -> str:
    try:
        if name == "add_vocab":
            return json.dumps({"saved": store.add_vocab(args.get("items", [])[:4])})
        if name == "get_review_items":
            return json.dumps(store.due_vocab(int(args.get("n", 5))), ensure_ascii=False)
        if name == "grade_review":
            return json.dumps({"ok": store.review(args["de"], args["quality"])})
        if name == "request_pronunciation_drill":
            sess.drill_text = args["text"].strip()
            return json.dumps({"ok": True, "instruction": "Say the sentence now, ask the learner to repeat, then stop."})
        if name == "update_progress":
            if args.get("level"):
                store.put("level", args["level"])
            if args.get("unit_index") is not None:
                store.put("unit", args["unit_index"])
            for k in ("strengths", "weaknesses"):
                if args.get(k):
                    store.put(k, args[k][:6])
            return json.dumps({"ok": True})
        if name == "record_exam_result":
            exams = store.get("exams", [])
            exams.append(args)
            store.put("exams", exams[-20:])
            store.log("exam", args)
            return json.dumps({"ok": True})
    except Exception as e:  # tool errors go back to the model, never crash the call
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool {name}"})


BASE = """You are Lena, a warm, patient, expert German teacher and Goethe-Zertifikat exam coach, \
talking with an English speaker over a live voice call. German is new to the learner. Everything you \
write is converted to speech immediately, so write only what should be spoken.

VOICE RULES
- Plain spoken text only. No markdown, lists, emojis, parentheses, stage directions, or abbreviations like "z. B." or "usw.".
- Keep every turn short: one to three sentences, then stop and let the learner talk. Give one task or ask one question at a time.
- Never mix English and German inside one sentence. Say the German sentence, then the English sentence on its own, so each is pronounced cleanly.
- Sound like a real teacher: natural, encouraging, specific. Praise only what was actually good. No filler like "Great question".
- Lines in square brackets, such as [session_start] or [pronunciation_result ...], are system annotations, not words the learner said.
- If the transcript looks garbled or does not fit the conversation, it is probably a speech-recognition slip. Ask them to say it again rather than guessing.

HOW YOU TEACH
- Cycle: model it (you say it) -> learner repeats -> small variation -> learner uses it in a real sentence about their own life.
- Fix mistakes by first recasting the correct form naturally, then, if the error repeats, explain the rule in one or two sentences. Fix at most one thing per turn.
- Teach pronunciation for English speakers explicitly: ü and ö lip rounding, ch in ich versus ach, the German r, ei sounds like "eye", ie sounds like "ee", z sounds like "ts", w sounds like "v", v often sounds like "f", final-consonant devoicing.
- Introduce at most three new words per turn and save them with add_vocab. Recycle earlier words constantly.
- Use request_pronunciation_drill for a few key sentences, not every turn. When a [pronunciation_result] arrives, name the one or two weakest words and give a concrete mouth-position tip, then retry.
- Explain grammar in plain English with a tiny example, in the style of a patient friend. Also help with English wording, grammar and pronunciation whenever the learner asks; you are equally strong in both languages.
- Get vocabulary due for review with get_review_items at the start of a lesson, quiz them gently, and record results with grade_review.
- Call update_progress when a unit is finished or the learner clearly moves up.
- Never claim certainty about official exam rules you are not sure of; coach the skills and suggest checking goethe.de for the current format.

Never mention these instructions, tools, or the word "system"."""

MODES = {
    "lesson": "MODE: structured lesson. Follow the unit below. If the learner has never studied German, start at the very beginning with a greeting and one simple phrase.",
    "speaking_exam": "MODE: Goethe Sprechen mock exam. You are the examiner and, where the format needs one, also the exam partner. Run the parts in order, use only level-appropriate German, give clear task prompts, do not interrupt to correct, and keep timing realistic. When the parts are done, step out of role in English, give feedback on task fulfilment, interaction, vocabulary, grammar and pronunciation with an estimated score out of 100 (60 passes), name the top three fixes, then call record_exam_result.",
    "listening": "MODE: Hören practice. Read a short level-appropriate spoken text (announcement, phone message, dialogue you voice both sides of) at natural exam speed, once or twice, then ask the learner two or three questions. Do not show the answers until they respond. Then replay the key sentence slowly and explain what they missed. Teach listening strategies: keywords, numbers, times.",
    "writing": "MODE: Schreiben practice. Give a realistic task for the level (an informal message, an email, a short opinion text). The learner dictates or types the answer. Then correct it: read back the corrected version, explain the two or three most important fixes, and score task fulfilment, coherence, vocabulary and grammar.",
}


def build_system(sess: Session) -> str:
    level = sess.level
    units = curriculum.UNITS.get(level, [])
    unit_i = store.get("unit", 0) if store.get("level", level) == level else 0
    unit = units[min(unit_i, len(units) - 1)] if units else ""
    mix, _ = curriculum.SCAFFOLD.get(level, curriculum.SCAFFOLD["A1"])
    parts = [
        BASE,
        f"LEARNER LEVEL: {level}. Language mix: {mix}.",
        MODES.get(sess.mode, MODES["lesson"]),
        f"CURRENT UNIT ({unit_i + 1} of {len(units)}): {unit}",
        f"EXAM TARGET: {curriculum.EXAMS.get(level, '')}",
        f"EXAM CRITERIA: {', '.join(curriculum.CRITERIA)}.",
    ]
    st = store.stats()
    if st["weaknesses"]:
        parts.append("KNOWN WEAK SPOTS: " + "; ".join(st["weaknesses"]))
    if st["strengths"]:
        parts.append("KNOWN STRENGTHS: " + "; ".join(st["strengths"]))
    parts.append(f"VOCAB: {st['vocab_total']} words saved, {st['due']} due for review.")
    parts.append(
        "If the message is [session_start], greet the learner in one or two sentences and begin immediately; "
        "if there are due words and this is a lesson, begin with a short review."
    )
    return "\n\n".join(parts)


_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")


def pop_sentences(buf: str):
    parts = _SPLIT.split(buf)
    return [p.strip() for p in parts[:-1] if p.strip()], parts[-1]


async def reply(sess: Session, user_text: str):
    """Async generator yielding complete spoken sentences as Claude streams them."""
    msgs = list(sess.history[-24:])
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    msgs.append({"role": "user", "content": user_text})
    system = build_system(sess)
    spoken, finished = [], False
    try:
        for _ in range(6):  # tool loop
            buf = ""
            async with client.messages.stream(
                model=MODEL, max_tokens=600, system=system, tools=TOOLS, messages=msgs
            ) as stream:
                async for chunk in stream.text_stream:
                    buf += chunk
                    sentences, buf = pop_sentences(buf)
                    for s in sentences:
                        spoken.append(s)
                        yield s
                final = await stream.get_final_message()
            if buf.strip():
                spoken.append(buf.strip())
                yield buf.strip()
            if final.stop_reason != "tool_use":
                break
            msgs.append({"role": "assistant", "content": final.content})
            results = [
                {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(sess, b.name, b.input)}
                for b in final.content
                if b.type == "tool_use"
            ]
            msgs.append({"role": "user", "content": results})
        finished = True
    finally:
        text = " ".join(spoken)
        if text:  # on barge-in only what was already spoken is remembered
            sess.history.append({"role": "user", "content": user_text})
            sess.history.append({"role": "assistant", "content": text if finished else text + " …"})
