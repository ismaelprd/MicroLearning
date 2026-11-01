import asyncio
import math
import os
import unicodedata

import flet as ft

import db
import gemini_service as ia

# ── Paleta: tinta azul, ámbar (acción) y turquesa (progreso) ─────────────────
TINTA = "#101626"
SUPERFICIE = "#1A2238"
SUPERFICIE_2 = "#243050"
AMBAR = "#F2B544"
TURQUESA = "#4FB3A5"
TEXTO = "#EDE9E0"
APAGADO = "#8A93A8"
ERROR = "#E5736B"

META_EXAMEN = 5  # historias necesarias para desbloquear el examen


def normalizar(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip().strip(".")


def main(page: ft.Page):
    page.title = "Cultura General"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = TINTA
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    sesion = {"usuario": None, "nombre": "", "nivel": 1, "estrellas": 0, "temas": [], "contenido": None}

    # ── Piezas reutilizables ────────────────────────────────────────────────
    def ancho():
        return min(460, (page.width or 460) - 40)

    def txt(texto, size=16, color=TEXTO, weight=None, align=None, **kw):
        return ft.Text(texto, size=size, color=color, weight=weight, text_align=align, **kw)

    def boton(texto, on_click, primario=True, color=None):
        fondo = color or (AMBAR if primario else SUPERFICIE_2)
        letra = TINTA if (primario or color) else TEXTO
        return ft.Button(
            content=ft.Text(texto, weight=ft.FontWeight.BOLD, color=letra, size=16),
            bgcolor=fondo,
            on_click=on_click,
            height=52,
            width=ancho(),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=14)),
        )

    def tarjeta(contenido, padding=18, bgcolor=SUPERFICIE, **kw):
        return ft.Container(content=contenido, padding=padding, bgcolor=bgcolor, border_radius=20, **kw)

    def mostrar(*controles):
        page.controls.clear()
        page.add(
            ft.Container(
                width=ancho(),
                expand=True,
                content=ft.Column(
                    list(controles),
                    scroll=ft.ScrollMode.AUTO,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                    expand=True,
                ),
            )
        )
        page.update()

    def mostrar_cargando(mensaje):
        page.controls.clear()
        page.add(
            ft.Column(
                [ft.ProgressRing(color=AMBAR), txt(mensaje, color=APAGADO)],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=18,
                expand=True,
            )
        )
        page.update()

    def barra_volver(destino):
        return ft.Row(
            [ft.IconButton(ft.Icons.ARROW_BACK, icon_color=TEXTO, on_click=lambda e: destino())],
            width=ancho(),
        )

    # ── Entrada ─────────────────────────────────────────────────────────────
    def mostrar_login(error=""):
        campo = ft.TextField(
            label="Tu nombre",
            autofocus=True,
            bgcolor=SUPERFICIE,
            border_color=SUPERFICIE_2,
            focused_border_color=AMBAR,
            border_radius=14,
            width=ancho(),
        )

        async def entrar(e):
            nombre = (campo.value or "").strip()
            if not nombre:
                mostrar_login("Escribe tu nombre para empezar.")
                return
            mostrar_cargando("Cargando tu progreso...")
            try:
                datos = await asyncio.to_thread(db.cargar_usuario, nombre.lower())
            except Exception as ex:
                mostrar_login(f"No se pudo conectar con la base de datos: {ex}")
                return
            sesion.update(
                usuario=nombre.lower(),
                nombre=nombre.title(),
                nivel=datos["nivel"],
                estrellas=datos["estrellas"],
                temas=datos["temas"],
            )
            mostrar_mapa()

        campo.on_submit = entrar

        mostrar(
            ft.Container(height=60),
            ft.Icon(ft.Icons.AUTO_STORIES, color=AMBAR, size=64),
            txt("Cultura general", size=38, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
            txt(
                "Una historia curiosa por nivel. Tu progreso se guarda con tu nombre.",
                color=APAGADO, align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=10),
            campo,
            txt(error, color=ERROR, size=14) if error else ft.Container(),
            boton("Empezar", entrar),
        )

    # ── Mapa de niveles ─────────────────────────────────────────────────────
    def mostrar_mapa():
        nivel = sesion["nivel"]
        temas = sesion["temas"]
        n = len(temas)

        cabecera = ft.Container(
            padding=22,
            border_radius=24,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT,
                end=ft.Alignment.BOTTOM_RIGHT,
                colors=[SUPERFICIE_2, SUPERFICIE],
            ),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            txt(f"Hola, {sesion['nombre']}", color=APAGADO),
                            ft.Row([ft.Icon(ft.Icons.STAR, color=AMBAR, size=22),
                                    txt(str(sesion["estrellas"]), size=20, weight=ft.FontWeight.BOLD)],
                                   spacing=4),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    txt(f"Nivel {nivel}", size=36, weight=ft.FontWeight.BOLD),
                    txt(ia.categoria_de_nivel(nivel), color=TURQUESA),
                    ft.ProgressBar(value=min(n / META_EXAMEN, 1), color=TURQUESA, bgcolor=TINTA, height=8),
                    txt(
                        "Examen de repaso disponible" if n >= META_EXAMEN
                        else f"{n} de {META_EXAMEN} historias para desbloquear el examen",
                        size=13, color=APAGADO,
                    ),
                ],
                spacing=8,
            ),
        )

        acciones = []
        if n >= META_EXAMEN:
            acciones.append(boton("Hacer el examen de repaso", iniciar_examen, color=TURQUESA))
        if n > 0:
            acciones.append(boton("Mis historias", lambda e: mostrar_biblioteca(), primario=False))

        camino = []
        for i in range(max(1, nivel - 6), nivel + 3):
            x = math.sin(i * 0.9) * 0.55
            if i < nivel:
                tema = temas[i - 1] if i - 1 < len(temas) else None
                circulo = ft.Container(
                    width=72, height=72, border_radius=36, bgcolor=TURQUESA,
                    alignment=ft.Alignment.CENTER, ink=True,
                    content=ft.Icon(ft.Icons.CHECK, color=TINTA, size=34),
                    on_click=(lambda e, t=tema: mostrar_tema_guardado(t, mostrar_mapa)) if tema else None,
                )
                etiqueta = tema["titulo"] if tema else ""
            elif i == nivel:
                circulo = ft.Container(
                    width=88, height=88, border_radius=44, bgcolor=AMBAR,
                    alignment=ft.Alignment.CENTER, ink=True,
                    content=ft.Icon(ft.Icons.PLAY_ARROW, color=TINTA, size=46),
                    shadow=ft.BoxShadow(blur_radius=28, color="#66F2B544", offset=ft.Offset(0, 6)),
                    on_click=iniciar_aprendizaje,
                )
                etiqueta = "Tu próxima historia"
            else:
                circulo = ft.Container(
                    width=64, height=64, border_radius=32, bgcolor=SUPERFICIE_2,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.LOCK, color=APAGADO, size=26),
                )
                etiqueta = ""

            camino.append(
                ft.Container(
                    width=ancho(),
                    alignment=ft.Alignment(x, 0),
                    content=ft.Column(
                        [circulo, txt(etiqueta, size=12, color=APAGADO, align=ft.TextAlign.CENTER,
                                      width=150, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                )
            )

        mostrar(cabecera, *acciones, ft.Container(height=6), *camino)

    # ── Lectura ─────────────────────────────────────────────────────────────
    def vista_lectura(contenido, acciones, volver=None):
        estilo = ft.MarkdownStyleSheet(
            p_text_style=ft.TextStyle(size=17, height=1.55, color=TEXTO),
            strong_text_style=ft.TextStyle(size=17, color=AMBAR, weight=ft.FontWeight.BOLD),
        )
        partes = []
        if volver:
            partes.append(barra_volver(volver))
        if contenido.get("categoria"):
            partes.append(txt(contenido["categoria"], color=TURQUESA, size=14))
        partes.append(txt(contenido["titulo"], size=30, weight=ft.FontWeight.BOLD))
        if contenido.get("imagen_url"):
            partes.append(
                ft.Image(src=contenido["imagen_url"], width=ancho(), height=210,
                         fit=ft.BoxFit.COVER, border_radius=18)
            )
        partes.append(
            ft.Markdown(contenido["texto"], selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, md_style_sheet=estilo)
        )
        partes.extend(acciones)
        mostrar(*partes)

    def mostrar_tema_guardado(tema, volver):
        vista_lectura(tema, [boton("Volver", lambda e: volver(), primario=False)], volver=volver)

    def mostrar_biblioteca():
        tarjetas = []
        for t in reversed(sesion["temas"]):
            tarjetas.append(
                tarjeta(
                    ft.Row(
                        [
                            ft.Column([txt(t["titulo"], size=17, weight=ft.FontWeight.BOLD),
                                       txt(f"Nivel {t['nivel']}", size=13, color=APAGADO)],
                                      spacing=2, expand=True),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=APAGADO),
                        ]
                    ),
                    ink=True,
                    on_click=lambda e, tema=t: mostrar_tema_guardado(tema, mostrar_biblioteca),
                )
            )
        mostrar(barra_volver(mostrar_mapa), txt("Mis historias", size=28, weight=ft.FontWeight.BOLD), *tarjetas)

    # ── Aprendizaje ─────────────────────────────────────────────────────────
    async def iniciar_aprendizaje(e=None):
        mostrar_cargando("Buscando una historia que no conoces...")
        titulos = [t["titulo"] for t in sesion["temas"]]
        contenido = await asyncio.to_thread(ia.generar_microaprendizaje, sesion["nivel"], titulos)

        if contenido.get("error"):
            mostrar(
                ft.Container(height=60),
                ft.Icon(ft.Icons.CLOUD_OFF, color=ERROR, size=56),
                txt(contenido["titulo"], size=24, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
                txt(contenido["texto"], color=APAGADO, align=ft.TextAlign.CENTER),
                boton("Reintentar", iniciar_aprendizaje),
                boton("Volver al mapa", lambda e: mostrar_mapa(), primario=False),
            )
            return

        sesion["contenido"] = contenido
        vista_lectura(
            contenido,
            [ft.Container(height=8), boton("Terminar y ganar una estrella", completar_nivel)],
            volver=mostrar_mapa,
        )

    async def completar_nivel(e):
        c = sesion["contenido"]
        nivel_completado = sesion["nivel"]
        sesion["temas"].append(
            {"titulo": c["titulo"], "texto": c["texto"], "imagen_url": c.get("imagen_url"), "nivel": nivel_completado}
        )
        sesion["estrellas"] += 1
        sesion["nivel"] += 1

        aviso = ""
        try:
            await asyncio.to_thread(
                db.guardar_tema_y_progreso, sesion["usuario"], nivel_completado,
                c["titulo"], c["texto"], c.get("imagen_url"), sesion["nivel"], sesion["estrellas"],
            )
        except Exception as ex:
            aviso = f"No se pudo guardar el progreso: {ex}"

        mostrar(
            ft.Container(height=60),
            ft.Icon(ft.Icons.STAR, color=AMBAR, size=110),
            txt("Nivel completado", size=30, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
            txt(f"Has ganado una estrella. El nivel {sesion['nivel']} ya está disponible.",
                color=APAGADO, align=ft.TextAlign.CENTER),
            txt(aviso, color=ERROR, size=13, align=ft.TextAlign.CENTER) if aviso else ft.Container(),
            ft.Container(height=10),
            boton("Volver al mapa", lambda e: mostrar_mapa()),
        )

    # ── Examen ──────────────────────────────────────────────────────────────
    async def iniciar_examen(e=None):
        mostrar_cargando("Preparando tu examen...")
        titulos = [t["titulo"] for t in sesion["temas"]]
        quiz = await asyncio.to_thread(ia.generar_quiz, titulos)
        preguntas = quiz.get("preguntas", [])

        if not preguntas:
            mostrar(
                ft.Container(height=60),
                ft.Icon(ft.Icons.CLOUD_OFF, color=ERROR, size=56),
                txt("No se pudo generar el examen", size=24, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
                boton("Reintentar", iniciar_examen),
                boton("Volver al mapa", lambda e: mostrar_mapa(), primario=False),
            )
            return

        entradas = []  # (pregunta, función que devuelve la respuesta)
        tarjetas = []
        for idx, p in enumerate(preguntas, start=1):
            tipo = p.get("tipo", "")
            if tipo in ("opcion_multiple", "verdadero_falso"):
                opciones = p.get("opciones") or ["Verdadero", "Falso"]
                grupo = ft.RadioGroup(content=ft.Column([ft.Radio(value=o, label=o) for o in opciones]))
                entradas.append((p, lambda g=grupo: g.value))
                control = grupo
            else:
                campo = ft.TextField(
                    hint_text="Tu respuesta", bgcolor=TINTA, border_color=SUPERFICIE_2,
                    focused_border_color=AMBAR, border_radius=12,
                    multiline=(tipo == "redactar"), min_lines=2 if tipo == "redactar" else 1,
                )
                entradas.append((p, lambda c=campo: c.value))
                control = campo
            tarjetas.append(
                tarjeta(ft.Column([txt(f"{idx}. {p['pregunta']}", weight=ft.FontWeight.BOLD), control], spacing=10))
            )

        async def corregir(e):
            resultados, aciertos, total = [], 0, 0
            for p, leer in entradas:
                dada = leer() or ""
                correcta = p.get("respuesta_correcta", "")
                if p.get("tipo") == "redactar":
                    estado = None  # respuesta abierta: se autoevalúa
                else:
                    total += 1
                    estado = normalizar(dada) == normalizar(correcta)
                    aciertos += 1 if estado else 0
                resultados.append((p, dada, correcta, estado))

            aviso = ""
            try:
                await asyncio.to_thread(db.guardar_examen, sesion["usuario"], aciertos, total)
            except Exception as ex:
                aviso = f"No se pudo guardar el resultado: {ex}"

            filas = []
            for p, dada, correcta, estado in resultados:
                icono, color = (
                    (ft.Icons.CHECK_CIRCLE, TURQUESA) if estado is True
                    else (ft.Icons.CANCEL, ERROR) if estado is False
                    else (ft.Icons.EDIT_NOTE, AMBAR)
                )
                detalle = [txt(p["pregunta"], weight=ft.FontWeight.BOLD, size=15)]
                if estado is not True:
                    detalle.append(txt(f"Tu respuesta: {dada or '(en blanco)'}", size=14, color=APAGADO))
                    detalle.append(txt(f"Respuesta de referencia: {correcta}", size=14, color=TEXTO))
                filas.append(
                    tarjeta(ft.Row([ft.Icon(icono, color=color, size=28),
                                    ft.Column(detalle, spacing=4, expand=True)],
                                   vertical_alignment=ft.CrossAxisAlignment.START, spacing=12))
                )

            mostrar(
                txt("Resultado", size=28, weight=ft.FontWeight.BOLD),
                tarjeta(
                    ft.Column(
                        [txt(f"{aciertos} de {total}", size=44, weight=ft.FontWeight.BOLD, color=AMBAR),
                         txt("respuestas correctas", color=APAGADO),
                         txt("La pregunta de redactar no puntúa: compárala con la respuesta de referencia.",
                             size=13, color=APAGADO)],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4,
                    ),
                    width=ancho(),
                ),
                txt(aviso, color=ERROR, size=13) if aviso else ft.Container(),
                *filas,
                boton("Volver al mapa", lambda e: mostrar_mapa()),
            )

        mostrar(
            barra_volver(mostrar_mapa),
            txt("Examen de repaso", size=28, weight=ft.FontWeight.BOLD),
            *tarjetas,
            boton("Corregir", corregir),
        )

    try:
        db.init_db()
        mostrar_login()
    except Exception as ex:
        mostrar_login(f"No se pudo preparar la base de datos: {ex}")


if __name__ == "__main__":
    ft.run(main, view=None, port=int(os.environ.get("PORT", 8080)))
