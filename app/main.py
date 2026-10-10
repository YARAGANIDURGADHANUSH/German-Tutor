import asyncio
import json
import logging
import pathlib

import httpx
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import curriculum, speech, store, tutor

log = logging.getLogger("sprechstunde")
app = FastAPI(title="Sprechstunde")
store.init()

LEVELS = set(curriculum.UNITS)
MODES = set(tutor.MODES)


@app.get("/api/progress")
def progress():
    return JSONResponse(store.stats())


async def produce(sess, user_text, q):
    """Stream Claude's sentences and start TTS for each one immediately, in parallel."""
    try:
        async for sentence in tutor.reply(sess, user_text):
            await q.put((sentence, asyncio.create_task(speech.tts(sentence, sess.rate))))
    finally:
        await q.put(None)


async def respond(ws: WebSocket, sess, user_text: str):
    sess.turn += 1
    await ws.send_json({"type": "turn_start", "id": sess.turn})
    q: asyncio.Queue = asyncio.Queue()
    prod = asyncio.create_task(produce(sess, user_text, q))
    try:
        while (item := await q.get()) is not None:
            sentence, fut = item
            await ws.send_json({"type": "say", "text": sentence})
            try:
                await ws.send_bytes(await fut)
            except httpx.HTTPError:
                await ws.send_json({"type": "say_failed"})
        await prod  # surface any error from the model call
        await ws.send_json({"type": "turn_done"})
    finally:
        prod.cancel()
        while not q.empty():
            item = q.get_nowait()
            if item:
                item[1].cancel()


async def transcribe_turn(ws: WebSocket, sess, wav: bytes):
    await ws.send_json({"type": "state", "value": "thinking"})
    if sess.drill_text:
        res = await speech.assess(wav, sess.drill_text)
        if not res:
            return None
        sess.drill_text = None
        await ws.send_json({"type": "pronunciation", **res["summary"]})
        await ws.send_json({"type": "transcript", "text": res["text"], "lang": "de-DE"})
        return f"{res['text']}\n[pronunciation_result {json.dumps(res['summary'], ensure_ascii=False)}]"
    res = await speech.transcribe(wav, sess.stt)
    if not res:
        return None
    await ws.send_json({"type": "transcript", "text": res["text"], "lang": res["lang"]})
    return res["text"]


async def run_turn(ws: WebSocket, sess, kind: str, payload):
    try:
        text = await transcribe_turn(ws, sess, payload) if kind == "audio" else payload
        if text:
            await respond(ws, sess, text)
        else:
            await ws.send_json({"type": "state", "value": "idle"})
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("turn failed")
        try:
            await ws.send_json({"type": "error", "message": str(e)[:240]})
            await ws.send_json({"type": "turn_done"})
        except Exception:
            pass


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    sess = tutor.Session()
    task: asyncio.Task | None = None

    async def cancel():
        nonlocal task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        task = None

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:  # one utterance (16 kHz mono WAV)
                await cancel()
                task = asyncio.create_task(run_turn(ws, sess, "audio", msg["bytes"]))
            elif msg.get("text") is not None:
                data = json.loads(msg["text"])
                kind = data.get("type")
                if kind == "start":
                    await cancel()
                    level = data.get("level", "A1")
                    sess.level = level if level in LEVELS else "A1"
                    sess.mode = data.get("mode") if data.get("mode") in MODES else "lesson"
                    sess.stt = data.get("stt", "auto")
                    sess.rate = curriculum.SCAFFOLD[sess.level][1]
                    sess.history, sess.drill_text = [], None
                    if store.get("level") != sess.level:
                        store.put("level", sess.level)
                        store.put("unit", 0)
                    task = asyncio.create_task(run_turn(ws, sess, "text", "[session_start]"))
                elif kind == "text" and data.get("text", "").strip():
                    await cancel()
                    task = asyncio.create_task(run_turn(ws, sess, "text", data["text"].strip()))
                elif kind == "interrupt":
                    await cancel()
                elif kind == "stt":
                    sess.stt = data.get("value", "auto")
    finally:
        await cancel()


app.mount(
    "/",
    StaticFiles(directory=pathlib.Path(__file__).resolve().parent.parent / "static", html=True),
    name="static",
)
