import asyncio

import flet as ft
from flet_audio_recorder import (
    AudioEncoder,
    AudioRecorder,
    AudioRecorderConfiguration,
    AudioRecorderStreamEvent,
)

from ia import ia
from multimedia import ia_media, pcm_a_wav


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
    estado = ft.Text()
    versos = ft.Column(spacing=8)
    boton = ft.Button(
        "Crear rima",
        style=ft.ButtonStyle(
            color=ft.Colors.BLACK,
            bgcolor=ft.Colors.CYAN_ACCENT,
        ),
    )
    boton_microfono = ft.IconButton(
        icon=ft.Icons.MIC,
        icon_color=ft.Colors.CYAN_ACCENT,
        tooltip="Dictar tema",
    )
    boton_foto = ft.Button("Leer texto y rimar una foto")
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
    grabando = False
    procesando_audio = False
    tarea_limite: asyncio.Task | None = None

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

    def mostrar_alerta(pagina: ft.Page, mensaje: str, color=ft.Colors.ORANGE):
        estado.value = mensaje
        estado.color = color
        pagina.update()

    def validar_texto(texto: str, pagina: ft.Page, origen: str) -> str | None:
        texto = texto.strip()
        if not texto:
            mostrar_alerta(pagina, f"No hay texto en {origen} para crear la rima.")
            return None
        if len(texto) > 500:
            mostrar_alerta(
                pagina,
                f"El texto de {origen} supera el límite de 500 caracteres.",
            )
            return None
        return texto

    def iniciar_carga(pagina: ft.Page, mensaje: str):
        for accion in (boton, boton_microfono, boton_foto, boton_texto):
            accion.disabled = True
        progreso.visible = True
        estado.value = mensaje
        estado.color = ft.Colors.CYAN_ACCENT
        pagina.update()

    def finalizar_carga(pagina: ft.Page):
        for accion in (boton, boton_microfono, boton_foto, boton_texto):
            accion.disabled = False
        progreso.visible = False
        pagina.update()

    def mostrar_versos(lista_versos: list[str]):
        versos.controls.clear()
        for numero, verso in enumerate(lista_versos, start=1):
            versos.controls.append(
                ft.Row(
                    [
                        ft.Text(
                            str(numero),
                            color=ft.Colors.CYAN_ACCENT,
                            weight=ft.FontWeight.BOLD,
                            width=28,
                        ),
                        ft.Text(verso.strip(), expand=True),
                    ],
                    spacing=8,
                )
            )

    async def crear_rima(tema: str, instruccion: str):
        respuesta = await asyncio.to_thread(ia, instruccion, tema, True)
        lista_versos = respuesta.get("versos") if isinstance(respuesta, dict) else None
        if (
            not isinstance(lista_versos, list)
            or len(lista_versos) != 4
            or any(not isinstance(verso, str) or not verso.strip() for verso in lista_versos)
        ):
            raise ValueError("La respuesta no contiene cuatro versos válidos.")
        mostrar_versos(lista_versos)

    async def generar(pagina: ft.Page):
        tema = validar_texto(entrada.value or "", pagina, "el tema")
        versos.controls.clear()
        if tema is None:
            return

        instruccion = (
            "Compón una rima original en español sobre el tema indicado. "
            "Devuelve únicamente un objeto JSON con la clave 'versos', "
            "cuyo valor sea una lista de exactamente cuatro versos. "
            "Los versos deben rimar entre sí."
        )

        iniciar_carga(pagina, "Componiendo...")
        try:
            await crear_rima(tema, instruccion)
            estado.value = ""
        except Exception:
            # Informa del fallo sin mostrar detalles técnicos al usuario.
            estado.value = "No pude crear la rima. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
        finally:
            finalizar_carga(pagina)

    async def rimar_foto(e):
        pagina = e.page
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
                fit=ft.ImageFit.CONTAIN,
                border_radius=8,
            )
            versos.controls.clear()
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
            if texto_extraido.upper() == "SIN_TEXTO":
                texto_extraido = ""
            texto_extraido = validar_texto(texto_extraido, pagina, "la imagen")
            if texto_extraido is None:
                texto_leido.value = "No se encontró texto legible en la imagen."
                return

            texto_leido.value = f"Texto leído: {texto_extraido}"
            estado.value = "Componiendo una rima con ese texto..."
            pagina.update()

            respuesta = await asyncio.to_thread(
                ia_media,
                "El texto explícito extraído de la imagen es: "
                f"«{texto_extraido}». Compón una rima original en español "
                "de exactamente cuatro versos que rime con esa frase y "
                "se inspire en su significado. Devuelve únicamente los "
                "cuatro versos, uno por línea.",
                imagen.bytes,
                "image/jpeg",
            )
            lista_versos = [
                linea.strip().lstrip("•*- ").removeprefix(f"{numero}.").strip()
                for numero, linea in enumerate(respuesta.splitlines(), start=1)
                if linea.strip()
            ]
            if len(lista_versos) != 4 or any(not verso for verso in lista_versos):
                raise ValueError("La respuesta no contiene cuatro versos.")

            mostrar_versos(lista_versos)
            estado.value = ""
        except Exception:
            # Muestra un aviso claro si la selección o la creación de la rima falla.
            estado.value = "No pude crear una rima con esa imagen. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
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
            versos.controls.clear()
            iniciar_carga(pagina, "Componiendo una rima inspirada en el documento...")

            respuesta = await asyncio.to_thread(
                ia,
                "Inspírate en el siguiente documento y compón una rima original "
                "en español de exactamente cuatro versos que lo resuma o refleje "
                "sus ideas. Devuelve únicamente un objeto JSON con la clave "
                "'versos', cuyo valor sea una lista de cuatro versos.",
                contenido,
                True,
            )
            lista_versos = respuesta.get("versos") if isinstance(respuesta, dict) else None
            if (
                not isinstance(lista_versos, list)
                or len(lista_versos) != 4
                or any(not isinstance(verso, str) or not verso.strip() for verso in lista_versos)
            ):
                raise ValueError("La respuesta no contiene cuatro versos válidos.")

            mostrar_versos(lista_versos)
            estado.value = ""
        except UnicodeDecodeError:
            # El documento debe estar guardado como texto UTF-8.
            estado.value = "No pude leer el archivo. Asegúrate de que esté codificado en UTF-8."
            estado.color = ft.Colors.RED
        except Exception:
            # Muestra un mensaje sencillo si falla la lectura o la composición.
            estado.value = "No pude crear una rima con ese documento. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
        finally:
            finalizar_carga(pagina)

    async def finalizar_grabacion(pagina: ft.Page):
        nonlocal grabando, procesando_audio, tarea_limite
        if not grabando or procesando_audio:
            return

        grabando = False
        procesando_audio = True
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
                "Transcribe en español el tema dictado. Devuelve únicamente "
                "el texto transcrito, sin explicaciones.",
                datos_wav,
                "audio/wav",
            )
            tema = validar_texto(
                transcripcion if isinstance(transcripcion, str) else "",
                pagina,
                "la transcripción",
            )
            if tema is None:
                return

            entrada.value = tema
            estado.value = "Componiendo..."
            pagina.update()
            await crear_rima(
                tema,
                "Compón una rima original en español sobre el tema indicado. "
                "Devuelve únicamente un objeto JSON con la clave 'versos', "
                "cuyo valor sea una lista de exactamente cuatro versos. "
                "Los versos deben rimar entre sí.",
            )
            estado.value = ""
            pagina.update()
        except Exception:
            # Mantiene un mensaje sencillo ante errores de grabación o transcripción.
            estado.value = "No pude procesar el audio. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
        finally:
            pcm.clear()
            procesando_audio = False
            finalizar_carga(pagina)

    async def detener_al_limite(pagina: ft.Page):
        await asyncio.sleep(30)
        await finalizar_grabacion(pagina)

    async def alternar_microfono(e):
        nonlocal grabando, tarea_limite
        pagina = e.page

        if grabando:
            await finalizar_grabacion(pagina)
            return

        url = (pagina.url or "").lower()
        if not url.startswith("https://"):
            estado.value = "Para grabar voz, abre esta app mediante HTTPS."
            estado.color = ft.Colors.ORANGE
            pagina.update()
            return

        try:
            registrar_grabadora(pagina)
            if not await grabadora.has_permission():
                estado.value = "Necesitas permitir el acceso al micrófono."
                estado.color = ft.Colors.ORANGE
                pagina.update()
                return

            pcm.clear()
            if not await grabadora.start_recording():
                mostrar_alerta(
                    pagina,
                    "No se pudo iniciar la grabación. Revisa el micrófono e inténtalo.",
                    ft.Colors.RED,
                )
                return

            grabando = True
            boton.disabled = True
            boton_foto.disabled = True
            boton_texto.disabled = True
            boton_microfono.icon = ft.Icons.STOP
            boton_microfono.tooltip = "Detener grabación"
            estado.value = "Grabando..."
            estado.color = ft.Colors.CYAN_ACCENT
            pagina.update()
            tarea_limite = asyncio.create_task(detener_al_limite(pagina))
        except Exception:
            # Explica el fallo sin exponer detalles técnicos de permisos o del dispositivo.
            estado.value = "No pude acceder al micrófono. Revisa los permisos e inténtalo."
            estado.color = ft.Colors.RED
            boton.disabled = False
            boton_foto.disabled = False
            boton_texto.disabled = False
            boton_microfono.icon = ft.Icons.MIC
            boton_microfono.tooltip = "Dictar tema"
            pagina.update()

    async def generar_desde_boton(e):
        await generar(e.page)

    boton.on_click = generar_desde_boton
    boton_microfono.on_click = alternar_microfono
    boton_foto.on_click = rimar_foto
    boton_texto.on_click = rimar_documento

    if page is not None:
        registrar_grabadora(page)
        registrar_selector(page)

    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    "Rimador",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.CYAN_ACCENT,
                ),
                entrada,
                ft.Row([boton, boton_microfono], spacing=8),
                boton_foto,
                boton_texto,
                nombre_foto,
                texto_leido,
                datos_documento,
                vista_previa,
                progreso,
                estado,
                versos,
            ],
            spacing=12,
            expand=True,
        ),
        bgcolor=ft.Colors.GREY_900,
        padding=16,
        border_radius=12,
        expand=True,
    )
