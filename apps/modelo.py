import asyncio

import flet as ft

from ia import ia


def vista() -> ft.Control:
    entrada = ft.TextField(
        label="¿Qué pasó?",
        hint_text="Cuéntame la situación...",
        multiline=True,
        min_lines=3,
        max_lines=5,
        expand=True,
    )
    estado = ft.Text()
    resultados = ft.Column(spacing=8)
    boton = ft.Button("Generar excusas")

    async def generar(e):
        situacion = (entrada.value or "").strip()
        resultados.controls.clear()

        if not situacion:
            estado.value = "Escribe qué pasó para poder ayudarte."
            estado.color = ft.Colors.ORANGE
            e.page.update()
            return

        boton.disabled = True
        estado.value = "Pensando excusas..."
        estado.color = None
        e.page.update()

        instruccion = (
            "Devuelve únicamente un objeto JSON con las claves "
            '"creible", "epica" y "absurda". Cada valor debe ser una '
            "excusa de una sola frase, basada en la situación. "
            "La creíble debe sonar realista, la épica grandiosa y "
            "la absurda disparatada."
        )

        try:
            respuesta = await asyncio.to_thread(ia, instruccion, situacion, True)
            if not isinstance(respuesta, dict) or any(
                not isinstance(respuesta.get(tipo), str)
                or not respuesta[tipo].strip()
                for tipo in ("creible", "epica", "absurda")
            ):
                raise ValueError("La respuesta no contiene las tres excusas esperadas.")

            for tipo, titulo in (
                ("creible", "Creíble"),
                ("epica", "Épica"),
                ("absurda", "Absurda"),
            ):
                resultados.controls.append(
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(titulo, weight=ft.FontWeight.BOLD),
                                ft.Text(respuesta[tipo].strip()),
                            ],
                            spacing=4,
                        ),
                        padding=12,
                        border=ft.border.all(1, ft.Colors.OUTLINE),
                        border_radius=8,
                    )
                )
            estado.value = ""
        except Exception:
            # Muestra un mensaje claro sin interrumpir la app si falla la IA.
            estado.value = "No pude generar las excusas. Inténtalo de nuevo."
            estado.color = ft.Colors.RED
        finally:
            boton.disabled = False
            e.page.update()

    boton.on_click = generar

    return ft.Column(
        [
            ft.Text("Excusas", size=24, weight=ft.FontWeight.BOLD),
            entrada,
            boton,
            estado,
            resultados,
        ],
        spacing=12,
        expand=True,
    )