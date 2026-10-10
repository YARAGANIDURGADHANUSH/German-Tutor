"""Speech in and out via Azure AI Speech (REST).

- transcribe(): speech-to-text. In "auto" mode it decodes the clip as both English and
  German and keeps the more confident result, so the learner can switch languages freely.
- assess(): pronunciation scoring of a German reference sentence (word-level).
- tts(): neural text-to-speech with a bilingual voice, returns MP3 bytes.
"""
import asyncio
import base64
import json
import os
from xml.sax.saxutils import escape

import httpx

KEY = os.environ.get("AZURE_SPEECH_KEY", "")
REGION = os.environ.get("AZURE_SPEECH_REGION", "westeurope")
VOICE = os.environ.get("TTS_VOICE", "de-DE-SeraphinaMultilingualNeural")
EN_LOCALE = os.environ.get("STT_EN_LOCALE", "en-IN")

STT_URL = f"https://{REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
TTS_URL = f"https://{REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

_http = httpx.AsyncClient(timeout=30)
WAV_TYPE = "audio/wav; codecs=audio/pcm; samplerate=16000"


async def _recognize(wav: bytes, lang: str, extra_headers=None):
    headers = {
        "Ocp-Apim-Subscription-Key": KEY,
        "Content-Type": WAV_TYPE,
        "Accept": "application/json",
        **(extra_headers or {}),
    }
    r = await _http.post(STT_URL, params={"language": lang, "format": "detailed"}, headers=headers, content=wav)
    r.raise_for_status()
    j = r.json()
    nbest = j.get("NBest") or []
    if j.get("RecognitionStatus") != "Success" or not nbest:
        return None
    return lang, nbest[0]


async def transcribe(wav: bytes, hint: str = "auto"):
    langs = {"en": [EN_LOCALE], "de": ["de-DE"]}.get(hint, [EN_LOCALE, "de-DE"])
    results = await asyncio.gather(*[_recognize(wav, l) for l in langs], return_exceptions=True)
    ok = [r for r in results if r and not isinstance(r, Exception)]
    if not ok:
        errs = [r for r in results if isinstance(r, Exception)]
        if errs:
            raise errs[0]
        return None
    lang, best = max(ok, key=lambda r: r[1].get("Confidence", 0))
    text = (best.get("Display") or best.get("Lexical") or "").strip()
    return {"text": text, "lang": lang, "confidence": best.get("Confidence", 0)} if text else None


async def assess(wav: bytes, reference: str):
    cfg = {
        "ReferenceText": reference,
        "GradingSystem": "HundredMark",
        "Granularity": "Word",
        "EnableMiscue": True,
    }
    header = base64.b64encode(json.dumps(cfg).encode()).decode()
    res = await _recognize(wav, "de-DE", {"Pronunciation-Assessment": header})
    if not res:
        return None
    _, nb = res
    pa = nb.get("PronunciationAssessment", {})
    weak = []
    for w in nb.get("Words", []):
        wpa = w.get("PronunciationAssessment", {})
        score, err = wpa.get("AccuracyScore"), wpa.get("ErrorType", "None")
        if (score is not None and score < 75) or err not in ("None", None):
            weak.append({"word": w.get("Word"), "score": score, "issue": err})
    return {
        "text": (nb.get("Display") or "").strip(),
        "summary": {
            "target": reference,
            "overall": pa.get("PronScore"),
            "accuracy": pa.get("AccuracyScore"),
            "fluency": pa.get("FluencyScore"),
            "completeness": pa.get("CompletenessScore"),
            "weak_words": weak,
        },
    }


async def tts(text: str, rate: str = "0%") -> bytes:
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='de-DE'>"
        f"<voice name='{VOICE}'><prosody rate='{rate}'>{escape(text)}</prosody></voice></speak>"
    )
    r = await _http.post(
        TTS_URL,
        headers={
            "Ocp-Apim-Subscription-Key": KEY,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": "sprechstunde",
        },
        content=ssml.encode("utf-8"),
    )
    r.raise_for_status()
    return r.content
