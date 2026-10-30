import json
import os

import httpx


MODELO = os.getenv("XAI_MODEL", "grok-4.7")
URL = "https://api.x.ai/v1/responses"


def validar_respuesta(respuesta):
    if respuesta.status_code == 200:
        return

    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}

    error = cuerpo.get("error", {}) if isinstance(cuerpo, dict) else {}
    mensaje = error.get("message") if isinstance(error, dict) else None
    estado = error.get("status") if isinstance(error, dict) else None
    detalle = f": {mensaje}" if isinstance(mensaje, str) and mensaje else ""
    if isinstance(estado, str) and estado:
        detalle = f" ({estado}){detalle}"

    raise RuntimeError(f"xAI respondió con error {respuesta.status_code}{detalle}")


def extraer_texto(respuesta):
    salida = respuesta.json()
    if isinstance(salida, dict) and isinstance(salida.get("output_text"), str):
        return salida["output_text"]

    bloques = []
    for elemento in salida.get("output", []):
        if not isinstance(elemento, dict) or elemento.get("type") != "message":
            continue
        for contenido in elemento.get("content", []):
            if (
                isinstance(contenido, dict)
                and contenido.get("type") == "output_text"
                and isinstance(contenido.get("text"), str)
            ):
                bloques.append(contenido["text"])
    if not bloques:
        raise RuntimeError("xAI devolvió una respuesta sin texto.")
    return "\n".join(bloques)


def analizar_json(contenido):
    contenido = (
        contenido.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    return json.loads(contenido)


def ia(instruccion, texto, como_json=False):
    """Envía texto a Grok y devuelve texto o datos JSON."""
    clave = os.getenv("XAI_API_KEY", "")
    if not clave:
        raise RuntimeError(
            "Falta XAI_API_KEY: configúrala en tu entorno o en los secretos del despliegue."
        )

    pedido = instruccion + "\n\nTexto: " + texto
    payload = {
        "model": MODELO,
        "input": pedido,
        "store": False,
    }
    if como_json:
        payload["text"] = {"format": {"type": "json_object"}}

    respuesta = httpx.post(
        URL,
        timeout=120,
        headers={"Authorization": f"Bearer {clave}"},
        json=payload,
    )
    validar_respuesta(respuesta)
    contenido = extraer_texto(respuesta)
    return analizar_json(contenido) if como_json else contenido
