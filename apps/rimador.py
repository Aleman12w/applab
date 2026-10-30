import asyncio
import inspect
import json
import re
from urllib.parse import quote

import flet as ft
from flet_audio_recorder import (
    AudioEncoder,
    AudioRecorder,
    AudioRecorderConfiguration,
    AudioRecorderStreamEvent,
)

from ia import ia
from multimedia import ia_media, ia_media_multimodal, pcm_a_wav

FORMATO_RIMA = (
    "Devuelve únicamente un objeto JSON con exactamente estos campos: "
    '"titulo", "verso1", "verso2", "verso3", "verso4" y "estilo". '
    "Todos los valores deben ser texto no vacío; cada verso debe ser una "
    "sola línea y los cuatro versos deben formar una rima."
)
MAX_GENERACIONES = 10
PATRONES_DATOS_SENSIBLES = (
    (
        re.compile(r"(?<!\d)\d{8}\s*-\s*\d(?!\d)"),
        "un número de DUI",
    ),
    (
        re.compile(
            r"\b(?:contrase(?:ñ|n)a|password|passwd|passphrase|clave)"
            r"\s*(?:es|:|=)\s*\S+",
            re.IGNORECASE,
        ),
        "una posible contraseña",
    ),
    (
        re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){7,15}(?!\d)"),
        "un posible número de teléfono",
    ),
)


def vista(page: ft.Page | None = None) -> ft.Control:
    entrada = ft.TextField(
        label="Tema",
        hint_text="¿Sobre qué quieres rimar?",
        multiline=True,
        min_lines=2,
        max_lines=4,
        expand=True,
        border_color=ft.Colors.CYAN,
        focused_border_color=ft.Colors.CYAN_ACCENT,
    )
    genero = ft.Dropdown(
        label="Género musical o estilo",
        value="Rap",
        options=[
            ft.DropdownOption(key=estilo, text=estilo)
            for estilo in ("Rap", "Bolero", "Reguetón", "Poesía Clásica")
        ],
        border_color=ft.Colors.CYAN,
        focused_border_color=ft.Colors.CYAN_ACCENT,
    )
    humor_valor = ft.Text("Humor: 3 / 5", color=ft.Colors.CYAN_ACCENT)
    humor = ft.Slider(
        min=1,
        max=5,
        divisions=4,
        value=3,
        label="{value}",
        active_color=ft.Colors.CYAN_ACCENT,
        on_change=lambda e: actualizar_humor(e),
    )
    estado = ft.Text()
    poema = ft.Column(spacing=8)
    historial = ft.Column(
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        height=240,
    )
    rimas_anteriores: list[dict[str, str]] = []
    rima_actual: dict[str, str] | None = None
    me_gusta = 0
    no_me_gusta = 0
    generaciones = 0
    contador_generaciones = ft.Text(
        f"Generaciones disponibles: {MAX_GENERACIONES}",
        color=ft.Colors.CYAN_ACCENT,
    )
    alerta_texto = ft.Text(color=ft.Colors.WHITE)
    tarjeta_alerta = ft.Card(
        content=ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.ORANGE),
                    alerta_texto,
                ],
                spacing=10,
            ),
            bgcolor="#3B2A17",
            border=ft.Border.all(1, ft.Colors.ORANGE),
            border_radius=10,
            padding=12,
        ),
        visible=False,
    )
    portapapeles = ft.Clipboard()
    lanzador_url = ft.UrlLauncher()
    boton = ft.Button(
        "Crear rima",
        style=ft.ButtonStyle(
            color=ft.Colors.BLACK,
            bgcolor=ft.Colors.CYAN_ACCENT,
        ),
    )
    boton_copiar = ft.Button("Copiar Rima", disabled=True)
    boton_me_gusta = ft.Button("👍", tooltip="Me gusta", disabled=True)
    boton_no_me_gusta = ft.Button("👎", tooltip="No me gusta", disabled=True)
    estadisticas_calificacion = ft.Text(
        "👍 0 me gusta  ·  👎 0 no me gusta",
        color=ft.Colors.CYAN_ACCENT,
    )
    boton_microfono = ft.IconButton(
        icon=ft.Icons.MIC,
        icon_color=ft.Colors.CYAN_ACCENT,
        tooltip="Dictar tema",
    )
    boton_foto = ft.Button("Leer texto y rimar una foto")
    boton_foto_voz = ft.Button("Rimar foto + instrucción de voz")
    boton_texto = ft.Button("Inspirar con un archivo .txt")
    nombre_foto = ft.Text()
    texto_leido = ft.Text()
    datos_documento = ft.Text()
    progreso = ft.ProgressRing(
        visible=False,
        color=ft.Colors.CYAN_ACCENT,
        width=24,
        height=24,
    )
    vista_previa = ft.Container()
    pcm = bytearray()
    imagen_para_audio: bytes | None = None
    grabando = False
    procesando_audio = False
    tarea_limite: asyncio.Task | None = None

    def actualizar_humor(e):
        humor_valor.value = f"Humor: {int(e.control.value)} / 5"
        e.page.update()

    def actualizar_calificacion(e, positiva: bool):
        nonlocal me_gusta, no_me_gusta
        if positiva:
            me_gusta += 1
        else:
            no_me_gusta += 1
        estadisticas_calificacion.value = (
            f"👍 {me_gusta} me gusta  ·  👎 {no_me_gusta} no me gusta"
        )
        e.page.update()

    def registrar_me_gusta(e):
        actualizar_calificacion(e, positiva=True)

    def registrar_no_me_gusta(e):
        actualizar_calificacion(e, positiva=False)

    def acumular_audio(e: AudioRecorderStreamEvent):
        pcm.extend(e.chunk)

    grabadora = AudioRecorder(
        configuration=AudioRecorderConfiguration(
            encoder=AudioEncoder.PCM16BITS,
            sample_rate=16000,
            channels=1,
        ),
        on_stream=acumular_audio,
    )
    selector = ft.FilePicker()

    def registrar_grabadora(pagina: ft.Page):
        if grabadora not in pagina.services:
            pagina.services.append(grabadora)

    def registrar_selector(pagina: ft.Page):
        if selector not in pagina.services:
            pagina.services.append(selector)

    def registrar_portapapeles(pagina: ft.Page):
        if portapapeles not in pagina.services:
            pagina.services.append(portapapeles)

    def registrar_lanzador_url(pagina: ft.Page):
        if lanzador_url not in pagina.services:
            pagina.services.append(lanzador_url)

    def actualizar_limite():
        disponibles = max(0, MAX_GENERACIONES - generaciones)
        contador_generaciones.value = (
            f"Generaciones disponibles: {disponibles} / {MAX_GENERACIONES}"
        )
        agotado = disponibles == 0
        boton.disabled = agotado
        boton_microfono.disabled = agotado
        boton_foto.disabled = agotado
        boton_foto_voz.disabled = agotado
        boton_texto.disabled = agotado

    def mostrar_alerta(pagina: ft.Page, mensaje: str, color=ft.Colors.ORANGE):
        estado.value = mensaje
        estado.color = color
        alerta_texto.value = mensaje
        alerta_texto.color = ft.Colors.WHITE
        tarjeta_alerta.content.content.controls[0].color = color
        tarjeta_alerta.content.border = ft.Border.all(1, color)
        tarjeta_alerta.content.bgcolor = (
            "#3B2A17" if color == ft.Colors.ORANGE else "#3B1D25"
        )
        tarjeta_alerta.visible = True
        pagina.update()

    def informar_error(pagina: ft.Page, error: Exception, mensaje: str):
        explicacion = mensaje
        if isinstance(error, RuntimeError):
            detalle = str(error).lower()
            if "429" in detalle or "rate limit" in detalle or "too many" in detalle:
                explicacion = (
                    "El servicio está recibiendo demasiadas solicitudes. "
                    "Espera un poco y vuelve a intentarlo."
                )
            elif "400" in detalle:
                explicacion = (
                    "La solicitud no pudo procesarse. Revisa el contenido e "
                    "inténtalo de nuevo."
                )
            elif any(
                palabra in detalle
                for palabra in ("network", "connection", "connect", "timeout", "red")
            ):
                explicacion = (
                    "No se pudo conectar con el servicio. Revisa tu conexión "
                    "a internet e inténtalo de nuevo."
                )
            else:
                explicacion = (
                    "El servicio de rimas tuvo un problema. Inténtalo de nuevo "
                    "dentro de unos momentos."
                )
        mostrar_alerta(pagina, explicacion, ft.Colors.RED)

    def reservar_generacion(pagina: ft.Page) -> bool:
        nonlocal generaciones
        if generaciones >= MAX_GENERACIONES:
            mostrar_alerta(
                pagina,
                "Has alcanzado el límite de 10 rimas para esta sesión.",
            )
            actualizar_limite()
            return False
        generaciones += 1
        actualizar_limite()
        return True

    def validar_texto(texto: str, pagina: ft.Page, origen: str) -> str | None:
        texto = texto.strip()
        if not texto:
            mostrar_alerta(pagina, f"No hay texto en {origen} para crear la rima.")
            return None
        for patron, tipo_dato in PATRONES_DATOS_SENSIBLES:
            if patron.search(texto):
                mostrar_alerta(
                    pagina,
                    f"Por privacidad, no puedo procesar {origen} porque contiene "
                    f"{tipo_dato}. Elimina ese dato y vuelve a intentarlo.",
                )
                return None
        if len(texto) > 500:
            mostrar_alerta(
                pagina,
                f"El texto de {origen} supera el límite de 500 caracteres.",
            )
            return None
        return texto

    def iniciar_carga(pagina: ft.Page, mensaje: str):
        tarjeta_alerta.visible = False
        for accion in (
            boton,
            boton_copiar,
            boton_microfono,
            boton_foto,
            boton_foto_voz,
            boton_texto,
            genero,
            humor,
        ):
            accion.disabled = True
        progreso.visible = True
        estado.value = mensaje
        estado.color = ft.Colors.CYAN_ACCENT
        pagina.update()

    def finalizar_carga(pagina: ft.Page):
        actualizar_limite()
        for accion in (genero, humor):
            accion.disabled = False
        boton_copiar.disabled = rima_actual is None
        progreso.visible = False
        pagina.update()

    def crear_tarjeta_rima(respuesta: dict, compacta: bool = False) -> ft.Control:
        contenido = [
            ft.Text(
                respuesta["titulo"].strip(),
                size=18 if not compacta else 16,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.CYAN_ACCENT,
            ),
            ft.Text(
                f"Estilo: {respuesta['estilo'].strip()}",
                italic=True,
                color=ft.Colors.CYAN_ACCENT,
            ),
            *[
                ft.Text(
                    respuesta[f"verso{numero}"].strip(),
                    size=15 if compacta else 16,
                )
                for numero in range(1, 5)
            ],
        ]
        if not compacta:
            contenido.append(
                ft.Button(
                    "Escuchar Rima",
                    icon=ft.Icons.VOLUME_UP,
                    on_click=escuchar_rima,
                    tooltip="Reproducir la rima en español",
                )
            )
        return ft.Card(
            content=ft.Container(
                content=ft.Column(contenido, spacing=6),
                padding=12 if compacta else 16,
            ),
            elevation=2,
        )

    async def escuchar_rima(e):
        pagina = e.page
        texto = texto_rima_actual()
        if not texto:
            return

        texto_js = json.dumps(texto, ensure_ascii=False)
        texto_js = (
            texto_js.replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        html = (
            "<!doctype html><html lang='es'><meta charset='utf-8'>"
            "<title>Escuchar rima</title><body>"
            "<p>Reproduciendo la rima...</p><script>"
            f"const texto={texto_js};"
            "const voz=new SpeechSynthesisUtterance(texto);"
            "voz.lang='es-ES';"
            "window.speechSynthesis.cancel();"
            "window.speechSynthesis.speak(voz);"
            "</script></body></html>"
        )
        url = "data:text/html;charset=utf-8," + quote(html, safe="")

        try:
            registrar_lanzador_url(pagina)
            await lanzador_url.launch_url(url, web_only_window_name="_blank")
        except Exception as error:
            informar_error(
                pagina,
                error,
                "No pude iniciar la lectura en voz alta en este navegador.",
            )
        finally:
            pagina.update()

    def mostrar_rima(respuesta: dict):
        poema.controls.clear()
        poema.controls.append(crear_tarjeta_rima(respuesta))

    def mostrar_historial():
        historial.controls.clear()
        for rima in reversed(rimas_anteriores):
            historial.controls.append(crear_tarjeta_rima(rima, compacta=True))

    def registrar_rima(respuesta: dict):
        nonlocal rima_actual
        if rima_actual is not None:
            rimas_anteriores.append(rima_actual.copy())
            del rimas_anteriores[:-5]
        rima_actual = respuesta.copy()
        boton_copiar.disabled = False
        boton_me_gusta.disabled = False
        boton_no_me_gusta.disabled = False
        mostrar_rima(rima_actual)
        mostrar_historial()

    def texto_rima_actual() -> str:
        if rima_actual is None:
            return ""
        return "\n".join(
            [
                rima_actual["titulo"].strip(),
                f"Estilo: {rima_actual['estilo'].strip()}",
                *[
                    rima_actual[f"verso{numero}"].strip()
                    for numero in range(1, 5)
                ],
            ]
        )

    async def copiar_rima(e):
        pagina = e.page
        texto = texto_rima_actual()
        if not texto:
            return

        try:
            metodo_copiar = getattr(pagina, "set_clipboard", None)
            if metodo_copiar is not None:
                resultado = metodo_copiar(texto)
                if inspect.isawaitable(resultado):
                    await resultado
            else:
                registrar_portapapeles(pagina)
                await portapapeles.set(texto)

            pagina.show_dialog(
                ft.SnackBar(
                    content="¡Rima copiada!",
                    duration=2500,
                    bgcolor=ft.Colors.GREEN_700,
                )
            )
            pagina.update()
        except Exception as error:
            informar_error(
                pagina,
                error,
                "No pude copiar la rima al portapapeles.",
            )

    def contexto_historial() -> str:
        recientes = [*rimas_anteriores, *([rima_actual] if rima_actual else [])][-5:]
        if not recientes:
            return ""

        texto = "\n".join(
            f"- {rima['titulo']}: "
            + " / ".join(rima[f"verso{numero}"] for numero in range(1, 5))
            for rima in recientes
        )
        return (
            "\n\nRimas recientes de esta sesión:\n"
            f"{texto}\n"
            "Mantén coherencia con el estilo, pero no repitas versos ni frases "
            "de estas rimas."
        )

    def aplicar_estilo(instruccion: str) -> str:
        estilo = genero.value or "Rap"
        nivel_humor = int(humor.value or 3)
        return (
            f"{instruccion}\n\nUsa estrictamente el género o estilo "
            f"«{estilo}»: adapta el ritmo, la métrica, la musicalidad y el "
            "vocabulario a sus convenciones. "
            f"El nivel de humor debe ser {nivel_humor} de 5 "
            "(1 = serio, 5 = muy humorístico)."
        )

    def validar_respuesta_rima(respuesta) -> dict:
        campos = ("titulo", "verso1", "verso2", "verso3", "verso4", "estilo")
        if not isinstance(respuesta, dict) or any(
            not isinstance(respuesta.get(campo), str)
            or not respuesta[campo].strip()
            for campo in campos
        ):
            raise ValueError("La respuesta no contiene todos los campos de la rima.")
        return respuesta

    async def crear_rima(tema: str, instruccion: str) -> dict:
        respuesta = await asyncio.to_thread(
            ia,
            f"{aplicar_estilo(instruccion)}\n\n"
            f"{FORMATO_RIMA}{contexto_historial()}",
            tema,
            como_json=True,
        )
        respuesta = validar_respuesta_rima(respuesta)
        registrar_rima(respuesta)
        return respuesta

    async def generar(pagina: ft.Page):
        tema = validar_texto(entrada.value or "", pagina, "el tema")
        if tema is None:
            return
        if not reservar_generacion(pagina):
            return

        instruccion = (
            "Compón una rima original en español sobre el tema indicado. "
            "Elige un título y un estilo apropiados para el poema."
        )

        iniciar_carga(pagina, "Componiendo...")
        try:
            await crear_rima(tema, instruccion)
            estado.value = ""
        except Exception as error:
            # Informa del fallo sin mostrar detalles técnicos al usuario.
            informar_error(
                pagina,
                error,
                "No pude crear la rima. Inténtalo de nuevo.",
            )
        finally:
            finalizar_carga(pagina)

    async def rimar_foto(e):
        pagina = e.page
        if generaciones >= MAX_GENERACIONES:
            reservar_generacion(pagina)
            return
        try:
            registrar_selector(pagina)
            seleccion = await selector.pick_files(
                file_type=ft.FilePickerFileType.IMAGE,
                with_data=True,
            )
            if not seleccion:
                return

            imagen = seleccion[0]
            if not imagen.bytes:
                estado.value = "No pude leer la imagen seleccionada."
                estado.color = ft.Colors.ORANGE
                pagina.update()
                return

            nombre_foto.value = imagen.name
            texto_leido.value = ""
            datos_documento.value = ""
            vista_previa.content = ft.Image(
                src=imagen.bytes,
                width=280,
                height=200,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
            )
            iniciar_carga(pagina, "Leyendo el texto de la imagen...")

            texto_extraido = await asyncio.to_thread(
                ia_media,
                "Extrae y transcribe únicamente el texto explícito y legible "
                "que aparece en esta imagen, como letreros, apuntes o frases. "
                "No describas la imagen. Si no hay texto visible, responde "
                "exactamente: SIN_TEXTO",
                imagen.bytes,
                "image/jpeg",
            )
            texto_extraido = (
                texto_extraido.strip() if isinstance(texto_extraido, str) else ""
            )
            if texto_extraido.upper() == "SIN_TEXTO" or not texto_extraido:
                texto_leido.value = "No se encontró texto legible en la imagen."
                estado.value = ""
                pagina.update()
                return
            texto_extraido = validar_texto(texto_extraido, pagina, "la imagen")
            if texto_extraido is None:
                return

            texto_leido.value = f"Texto leído: {texto_extraido}"
            estado.value = "Componiendo una rima con ese texto..."
            pagina.update()
            if not reservar_generacion(pagina):
                return

            respuesta = await asyncio.to_thread(
                ia_media,
                aplicar_estilo(
                    "El texto explícito extraído de la imagen es: "
                    f"«{texto_extraido}». Compón una rima original en español "
                    "de exactamente cuatro versos que rime con esa frase y "
                    "se inspire en su significado. Elige un título y describe "
                    "el estilo del poema."
                )
                + "\n\n"
                + FORMATO_RIMA
                + contexto_historial(),
                imagen.bytes,
                "image/jpeg",
                como_json=True,
            )
            respuesta = validar_respuesta_rima(respuesta)
            registrar_rima(respuesta)
            estado.value = ""
        except Exception as error:
            # Muestra un aviso claro si la selección o la creación de la rima falla.
            informar_error(
                pagina,
                error,
                "No pude crear una rima con esa imagen. Inténtalo de nuevo.",
            )
        finally:
            finalizar_carga(pagina)

    async def rimar_documento(e):
        pagina = e.page
        try:
            registrar_selector(pagina)
            seleccion = await selector.pick_files(
                allowed_extensions=["txt"],
                file_type=ft.FilePickerFileType.CUSTOM,
                with_data=True,
            )
            if not seleccion:
                return

            archivo = seleccion[0]
            if not archivo.bytes:
                estado.value = "El archivo está vacío o no se pudo leer."
                estado.color = ft.Colors.ORANGE
                pagina.update()
                return

            contenido = validar_texto(
                archivo.bytes.decode("utf-8"),
                pagina,
                "el archivo",
            )
            if contenido is None:
                return

            # El recuento se obtiene localmente antes de enviar el documento a la IA.
            cantidad_palabras = len(contenido.split())
            nombre_foto.value = ""
            texto_leido.value = ""
            vista_previa.content = None
            datos_documento.value = (
                f"Archivo: {archivo.name} · {cantidad_palabras} palabras"
            )
            if not reservar_generacion(pagina):
                return
            iniciar_carga(pagina, "Componiendo una rima inspirada en el documento...")

            await crear_rima(
                contenido,
                "Inspírate en el siguiente documento y compón una rima original "
                "en español que lo resuma o refleje sus ideas. Elige un título "
                "y describe el estilo del poema.",
            )
            estado.value = ""
        except UnicodeDecodeError as error:
            # El documento debe estar guardado como texto UTF-8.
            informar_error(
                pagina,
                error,
                "No pude leer el archivo. Asegúrate de que esté codificado en UTF-8.",
            )
        except Exception as error:
            # Muestra un mensaje sencillo si falla la lectura o la composición.
            informar_error(
                pagina,
                error,
                "No pude crear una rima con ese documento. Inténtalo de nuevo.",
            )
        finally:
            finalizar_carga(pagina)

    async def finalizar_grabacion(pagina: ft.Page):
        nonlocal grabando, procesando_audio, tarea_limite, imagen_para_audio
        if not grabando or procesando_audio:
            return

        grabando = False
        procesando_audio = True
        imagen = imagen_para_audio
        if tarea_limite is not None and tarea_limite is not asyncio.current_task():
            tarea_limite.cancel()
        tarea_limite = None
        boton_microfono.disabled = True
        boton_microfono.icon = ft.Icons.MIC
        boton_microfono.tooltip = "Dictar tema"
        iniciar_carga(pagina, "Transcribiendo...")

        try:
            await grabadora.stop_recording()
            if not pcm:
                mostrar_alerta(pagina, "No se recibió audio. Inténtalo de nuevo.")
                return

            datos_wav = pcm_a_wav(bytes(pcm))
            pcm.clear()
            transcripcion = await asyncio.to_thread(
                ia_media,
                "Transcribe en español el tema o la instrucción dictada. Devuelve únicamente "
                "el texto transcrito, sin explicaciones.",
                datos_wav,
                "audio/wav",
            )
            tema = validar_texto(
                transcripcion if isinstance(transcripcion, str) else "",
                pagina,
                "la instrucción dictada" if imagen else "la transcripción",
            )
            if tema is None:
                return
            if not reservar_generacion(pagina):
                return

            entrada.value = tema
            if imagen:
                texto_leido.value = f"Instrucción de voz: {tema}"
                estado.value = "Componiendo una rima con la imagen y la voz..."
            else:
                estado.value = "Componiendo..."
            pagina.update()
            if imagen:
                instruccion = aplicar_estilo(
                    "Usa conjuntamente la imagen y el audio adjuntos. La imagen "
                    "aporta el objeto o lugar que inspira el poema; sigue la "
                    "instrucción hablada para decidir el enfoque, tono o estilo. "
                    "Compón en español una rima original de exactamente cuatro "
                    "versos que se ajuste a ambos insumos. La transcripción de "
                    "la instrucción hablada también se incluye como texto."
                )
                respuesta = await asyncio.to_thread(
                    ia_media_multimodal,
                    instruccion + "\n\n" + FORMATO_RIMA,
                    [(imagen, "image/jpeg"), (datos_wav, "audio/wav")],
                    f"Instrucción dictada: {tema}{contexto_historial()}",
                    True,
                )
                respuesta = validar_respuesta_rima(respuesta)
                registrar_rima(respuesta)
            else:
                await crear_rima(
                    tema,
                    "Compón una rima original en español sobre el tema indicado. "
                    "Elige un título y un estilo apropiados para el poema.",
                )
            estado.value = ""
            pagina.update()
        except Exception as error:
            # Mantiene un mensaje sencillo ante errores de grabación o transcripción.
            informar_error(
                pagina,
                error,
                "No pude procesar el audio. Inténtalo de nuevo.",
            )
        finally:
            pcm.clear()
            procesando_audio = False
            imagen_para_audio = None
            finalizar_carga(pagina)

    async def detener_al_limite(pagina: ft.Page):
        await asyncio.sleep(30)
        await finalizar_grabacion(pagina)

    async def iniciar_grabacion(pagina: ft.Page, imagen: bytes | None = None):
        nonlocal grabando, tarea_limite, imagen_para_audio
        if generaciones >= MAX_GENERACIONES:
            reservar_generacion(pagina)
            return

        url = (pagina.url or "").lower()
        if not url.startswith("https://"):
            mostrar_alerta(
                pagina,
                "Para grabar voz, abre esta app mediante HTTPS.",
            )
            return

        try:
            registrar_grabadora(pagina)
            if not await grabadora.has_permission():
                mostrar_alerta(pagina, "Necesitas permitir el acceso al micrófono.")
                return

            pcm.clear()
            if not await grabadora.start_recording():
                mostrar_alerta(
                    pagina,
                    "No se pudo iniciar la grabación. Revisa el micrófono e inténtalo.",
                    ft.Colors.RED,
                )
                return

            imagen_para_audio = imagen
            grabando = True
            boton.disabled = True
            boton_foto.disabled = True
            boton_foto_voz.disabled = True
            boton_texto.disabled = True
            boton_microfono.icon = ft.Icons.STOP
            boton_microfono.tooltip = "Detener grabación"
            estado.value = (
                "Grabando... Describe en voz alta el estilo o la instrucción para la rima."
                if imagen
                else "Grabando..."
            )
            estado.color = ft.Colors.CYAN_ACCENT
            pagina.update()
            tarea_limite = asyncio.create_task(detener_al_limite(pagina))
        except Exception as error:
            # Explica el fallo sin exponer detalles técnicos de permisos o del dispositivo.
            imagen_para_audio = None
            informar_error(
                pagina,
                error,
                "No pude acceder al micrófono. Revisa los permisos e inténtalo.",
            )
            actualizar_limite()
            boton_microfono.icon = ft.Icons.MIC
            boton_microfono.tooltip = "Dictar tema"
            pagina.update()

    async def rimar_foto_con_voz(e):
        pagina = e.page
        if generaciones >= MAX_GENERACIONES:
            reservar_generacion(pagina)
            return

        try:
            registrar_selector(pagina)
            seleccion = await selector.pick_files(
                file_type=ft.FilePickerFileType.IMAGE,
                with_data=True,
            )
            if not seleccion:
                return

            imagen = seleccion[0]
            if not imagen.bytes:
                mostrar_alerta(pagina, "No pude leer la imagen seleccionada.")
                return

            nombre_foto.value = imagen.name
            texto_leido.value = ""
            datos_documento.value = ""
            vista_previa.content = ft.Image(
                src=imagen.bytes,
                width=280,
                height=200,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
            )
            pagina.update()
            await iniciar_grabacion(pagina, imagen.bytes)
        except Exception as error:
            informar_error(
                pagina,
                error,
                "No pude preparar la foto y la grabación. Inténtalo de nuevo.",
            )

    async def alternar_microfono(e):
        pagina = e.page
        if grabando:
            await finalizar_grabacion(pagina)
            return
        await iniciar_grabacion(pagina)

    async def generar_desde_boton(e):
        await generar(e.page)

    boton.on_click = generar_desde_boton
    boton_copiar.on_click = copiar_rima
    boton_me_gusta.on_click = registrar_me_gusta
    boton_no_me_gusta.on_click = registrar_no_me_gusta
    boton_microfono.on_click = alternar_microfono
    boton_foto.on_click = rimar_foto
    boton_foto_voz.on_click = rimar_foto_con_voz
    boton_texto.on_click = rimar_documento

    if page is not None:
        registrar_grabadora(page)
        registrar_selector(page)

    return ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        content=ft.Icon(
                                            ft.Icons.MIC,
                                            color="#F0ABFC",
                                            size=28,
                                        ),
                                        bgcolor="#3B1D45",
                                        padding=12,
                                        border_radius=14,
                                    ),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                "Rimador 🎤",
                                                size=30,
                                                weight=ft.FontWeight.BOLD,
                                                color="#22D3EE",
                                            ),
                                            ft.Text(
                                                "CREATIVIDAD EN VERSO",
                                                size=11,
                                                weight=ft.FontWeight.BOLD,
                                                color="#E879F9",
                                            ),
                                        ],
                                        spacing=2,
                                    ),
                                ],
                                spacing=14,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(color="#334155", height=1),
                            ft.Column(
                                [
                                    ft.Text(
                                        "Crea versos originales y rimas a partir de un tema, tu voz, una imagen o un texto.",
                                        color="#E2E8F0",
                                    ),
                                    ft.Text(
                                        "Personaliza el estilo y el humor; después, escucha o copia tu rima.",
                                        color="#CBD5E1",
                                    ),
                                    ft.Text(
                                        "Rimador no genera canciones completas ni audio musical: crea poemas en texto.",
                                        color="#F0ABFC",
                                    ),
                                ],
                                spacing=6,
                            ),
                        ],
                        spacing=12,
                    ),
                    bgcolor="#111827",
                    border=ft.Border.all(1, "#22D3EE"),
                    border_radius=18,
                    padding=20,
                ),
                ft.Text(
                    "La IA puede cometer errores. Verifica la información.",
                    color="#CBD5E1",
                    size=12,
                    italic=True,
                ),
                entrada,
                contador_generaciones,
                genero,
                humor_valor,
                humor,
                ft.Row([boton, boton_microfono], spacing=8),
                boton_copiar,
                boton_foto,
                boton_foto_voz,
                boton_texto,
                nombre_foto,
                texto_leido,
                datos_documento,
                vista_previa,
                progreso,
                tarjeta_alerta,
                estado,
                ft.Text(
                    "Rima actual",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.CYAN_ACCENT,
                ),
                poema,
                ft.Row(
                    [boton_me_gusta, boton_no_me_gusta],
                    spacing=8,
                ),
                ft.Text(
                    "Historial de rimas anteriores",
                    size=18,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.CYAN_ACCENT,
                ),
                historial,
                ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Estadísticas de esta sesión",
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.CYAN_ACCENT,
                                ),
                                estadisticas_calificacion,
                            ],
                            spacing=6,
                        ),
                        padding=14,
                    ),
                    elevation=2,
                ),
            ],
            spacing=12,
            expand=True,
        ),
        bgcolor=ft.Colors.GREY_900,
        padding=16,
        border_radius=12,
        expand=True,
    )
