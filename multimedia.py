import base64
import io
import os
import wave

import httpx

from ia import URL, analizar_json, extraer_texto, validar_respuesta


URL_TRANSCRIPCION = "https://api.x.ai/v1/stt"
MODELO_TRANSCRIPCION = "grok-voice-transcribe-2.0"
MAX_ARCHIVO = 15_000_000


def pcm_a_wav(pcm, tasa=16000, canales=1):
    """Convierte audio PCM de 16 bits en un archivo WAV."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(canales)
        wav.setsampwidth(2)
        wav.setframerate(tasa)
        wav.writeframes(pcm)
    return buf.getvalue()


def _clave_api():
    clave = os.getenv("XAI_API_KEY", "")
    if not clave:
        raise RuntimeError(
            "Falta XAI_API_KEY: configúrala en tu entorno o en los secretos del despliegue."
        )
    return clave


def _transcribir_audio(datos, mime):
    if len(datos) > MAX_ARCHIVO:
        raise RuntimeError("El audio es muy grande (máximo 15 MB).")
    extensiones = {
        "audio/wav": ("audio.wav", "audio/wav"),
        "audio/x-wav": ("audio.wav", "audio/wav"),
        "audio/mpeg": ("audio.mp3", "audio/mpeg"),
        "audio/mp3": ("audio.mp3", "audio/mpeg"),
        "audio/webm": ("audio.webm", "audio/webm"),
        "audio/ogg": ("audio.ogg", "audio/ogg"),
        "audio/mp4": ("audio.mp4", "audio/mp4"),
    }
    archivo = extensiones.get(mime)
    if archivo is None:
        raise RuntimeError(f"xAI no admite el formato de audio {mime}.")

    respuesta = httpx.post(
        URL_TRANSCRIPCION,
        timeout=120,
        headers={"Authorization": f"Bearer {_clave_api()}"},
        data=[("model", MODELO_TRANSCRIPCION), ("language", "es")],
        files=[("file", (archivo[0], datos, archivo[1]))],
    )
    validar_respuesta(respuesta)
    transcripcion = respuesta.json().get("text")
    if not isinstance(transcripcion, str):
        raise RuntimeError("xAI devolvió una transcripción de audio inválida.")
    return transcripcion


def _generar_multimodal(instruccion, archivos, texto="", como_json=False):
    partes = []
    for datos, mime in archivos:
        if len(datos) > MAX_ARCHIVO:
            raise RuntimeError("El archivo es muy grande (máximo 15 MB).")
        if mime.startswith("audio/"):
            transcripcion = _transcribir_audio(datos, mime)
            partes.append(
                {
                    "type": "input_text",
                    "text": f"Transcripción del audio adjunto: {transcripcion}",
                }
            )
        elif mime in ("image/jpeg", "image/png"):
            imagen = base64.b64encode(datos).decode("ascii")
            partes.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime};base64,{imagen}",
                    "detail": "high",
                }
            )
        else:
            raise RuntimeError(f"xAI no admite el formato de archivo {mime}.")

    pedido = instruccion + ("\n\nTexto: " + texto if texto else "")
    partes.append({"type": "input_text", "text": pedido})
    payload = {
        "model": os.getenv("XAI_MODEL", "grok-4.7"),
        "input": [{"role": "user", "content": partes}],
        "store": False,
    }
    if como_json:
        payload["text"] = {"format": {"type": "json_object"}}

    respuesta = httpx.post(
        URL,
        timeout=120,
        headers={"Authorization": f"Bearer {_clave_api()}"},
        json=payload,
    )
    validar_respuesta(respuesta)
    contenido = extraer_texto(respuesta)
    return analizar_json(contenido) if como_json else contenido


def ia_media(instruccion, datos, mime, texto="", como_json=False):
    """Envía una imagen a Grok o transcribe audio con xAI."""
    if mime.startswith("audio/"):
        return _transcribir_audio(datos, mime)
    return _generar_multimodal(
        instruccion,
        [(datos, mime)],
        texto,
        como_json,
    )


def ia_media_multimodal(instruccion, archivos, texto="", como_json=False):
    """Envía imágenes y transcripciones de audio a Grok en una petición."""
    return _generar_multimodal(instruccion, archivos, texto, como_json)
