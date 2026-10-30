import asyncio

import flet as ft

from ia import ia


def vista() -> ft.Control:
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

    async def generar(e):
        tema = (entrada.value or "").strip()
        versos.controls.clear()

        if not tema:
            estado.value = "Escribe un tema para crear tu rima."
            estado.color = ft.Colors.ORANGE
            e.page.update()
            return

        boton.disabled = True
        estado.value = "Componiendo..."
        estado.color = ft.Colors.CYAN_ACCENT
        e.page.update()

        instruccion = (
            "Compón una rima original en español sobre el tema indicado. "
            "Devuelve únicamente un objeto JSON con la clave 'versos', "
            "cuyo valor sea una lista de exactamente cuatro versos. "
            "Los versos deben rimar entre sí."
        )

        try:
            respuesta = await asyncio.to_thread(ia, instruccion, tema, True)
            lista_versos = respuesta.get("versos") if isinstance(respuesta, dict) else None
            if (
                not isinstance(lista_versos, list)
                or len(lista_versos) != 4
                or any(not isinstance(verso, str) or not verso.strip() for verso in lista_versos)
            ):
                raise ValueError("La respuesta no contiene cuatro versos válidos.")

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
            estado.value = ""
        except Exception:
            # Informa del fallo sin mostrar detalles técnicos al usuario.
            estado.value = "No pude crear la rima. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
        finally:
            boton.disabled = False
            e.page.update()

    boton.on_click = generar

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
                boton,
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
