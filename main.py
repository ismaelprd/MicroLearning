import asyncio
import math
import os
import re
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
AZUL = "#7C9CF2"
TEXTO = "#EDE9E0"
APAGADO = "#8A93A8"
ERROR = "#E5736B"

META_EXAMEN = 5  # historias necesarias para desbloquear el examen (después incluye TODAS)
MIN_PALABRAS = 5  # palabras guardadas necesarias para el test de vocabulario
CLAVE_NOMBRE = "genk_usuario"  # clave donde el navegador recuerda quién eres

# Frases: corta en . ! ? … (con comillas/paréntesis de cierre opcionales) seguidos de espacio o fin.
_FRASES = re.compile(r".+?(?:[.!?…]+[\"'”’)\]]*(?=\s|$)|$)", re.S)
# Palabras: letras (con acentos), admite contracciones (don't) y guiones (well-known).
_PALABRAS = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")


def normalizar(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip().strip(".")


async def main(page: ft.Page):
    page.title = "GenK"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = TINTA
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    sesion = {
        "usuario": None, "nombre": "", "nivel": 1, "estrellas": 0, "temas": [],
        "palabras": {},            # termino -> datos de la palabra guardada
        "contenido": None,         # historia abierta ahora mismo
        "contenido_nivel": None,   # nivel al que pertenece esa historia
        "cargando": False,         # evita abrir/generar la historia dos veces a la vez
        "completando": False,      # evita completar el nivel dos veces
        "cache_trad": {},          # (termino, frase) -> traducción en contexto
        "cache_frases": {},        # frase -> traducción
        "cache_es": {},            # título -> historia completa traducida
    }

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

    def pantalla_error(titulo, reintentar, detalle=""):
        mostrar(
            ft.Container(height=60),
            ft.Icon(ft.Icons.CLOUD_OFF, color=ERROR, size=56),
            txt(titulo, size=24, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
            txt(detalle, color=APAGADO, align=ft.TextAlign.CENTER) if detalle else ft.Container(),
            boton("Reintentar", reintentar),
            boton("Volver al mapa", lambda e: mostrar_mapa(), primario=False),
        )

    # ── Recordar al usuario en este dispositivo/navegador ────────────────────
    async def leer_pref(clave):
        try:
            return await ft.SharedPreferences().get(clave)
        except Exception:
            try:  # compatibilidad con versiones antiguas de Flet
                return await page.client_storage.get_async(clave)
            except Exception:
                return None

    async def guardar_pref(clave, valor):
        try:
            await ft.SharedPreferences().set(clave, valor)
        except Exception:
            try:
                await page.client_storage.set_async(clave, valor)
            except Exception as ex:
                print(f"No se pudo recordar el usuario: {ex}")

    async def borrar_pref(clave):
        try:
            await ft.SharedPreferences().remove(clave)
        except Exception:
            try:
                await page.client_storage.remove_async(clave)
            except Exception as ex:
                print(f"No se pudo olvidar el usuario: {ex}")

    async def iniciar_sesion(nombre):
        """Carga el progreso (historias y palabras) desde Turso y abre el mapa."""
        nombre = nombre.strip().lower()
        mostrar_cargando("Cargando tu progreso...")
        try:
            datos = await asyncio.to_thread(db.cargar_usuario, nombre)
        except Exception as ex:
            mostrar_login(f"No se pudo conectar con la base de datos: {ex}")
            return
        sesion.update(
            usuario=nombre,
            nombre=nombre.title(),
            nivel=datos["nivel"],
            estrellas=datos["estrellas"],
            temas=datos["temas"],
            palabras=datos["palabras"],
            contenido=None,
            contenido_nivel=None,
        )
        await guardar_pref(CLAVE_NOMBRE, nombre)
        mostrar_mapa()

    async def cambiar_usuario(e):
        await borrar_pref(CLAVE_NOMBRE)
        sesion.update(usuario=None, nombre="", temas=[], palabras={}, contenido=None, contenido_nivel=None)
        mostrar_login()

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
            await iniciar_sesion(nombre)

        campo.on_submit = entrar

        mostrar(
            ft.Container(height=60),
            ft.Icon(ft.Icons.AUTO_STORIES, color=AMBAR, size=64),
            txt("GenK", size=44, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
            txt(
                "Una historia por nivel, en inglés. Tu progreso se guarda con tu nombre.",
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
        n_palabras = len(sesion["palabras"])
        temas_por_nivel = {t["nivel"]: t for t in temas}

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
                        f"Examen de historias disponible (incluye tus {n})" if n >= META_EXAMEN
                        else f"{n} de {META_EXAMEN} historias para desbloquear el examen",
                        size=13, color=APAGADO,
                    ),
                    txt(
                        f"Vocabulario: {n_palabras} guardadas" if n_palabras >= MIN_PALABRAS
                        else f"Vocabulario: {n_palabras} de {MIN_PALABRAS} palabras para desbloquear el test",
                        size=13, color=APAGADO,
                    ),
                ],
                spacing=8,
            ),
        )

        acciones = []
        if n >= META_EXAMEN:
            acciones.append(boton("Examen de historias", iniciar_examen, color=TURQUESA))
        if n_palabras >= MIN_PALABRAS:
            acciones.append(boton("Test de vocabulario", iniciar_test_vocabulario, color=AZUL))
        if n > 0:
            acciones.append(boton("Mis historias", lambda e: mostrar_biblioteca(), primario=False))
        if n_palabras > 0:
            acciones.append(boton("Mis palabras", lambda e: mostrar_palabras(), primario=False))

        camino = []
        for i in range(max(1, nivel - 6), nivel + 3):
            x = math.sin(i * 0.9) * 0.55
            if i < nivel:
                tema = temas_por_nivel.get(i)
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

        cambiar = ft.TextButton(content=ft.Text("Cambiar de usuario", color=APAGADO, size=13),
                                on_click=cambiar_usuario)
        mostrar(cabecera, *acciones, ft.Container(height=6), *camino, ft.Container(height=10), cambiar)

    # ── Lectura interactiva ─────────────────────────────────────────────────
    async def guardar_termino(termino, traduccion, frase, nivel, es_frase=False):
        """Guarda la palabra/frase tocada. Devuelve True si se pudo guardar."""
        try:
            await asyncio.to_thread(
                db.guardar_palabra, sesion["usuario"], termino, traduccion, frase, nivel, es_frase
            )
        except Exception as ex:
            print(f"No se pudo guardar la palabra: {ex}")
            return False
        previa = sesion["palabras"].get(termino)
        sesion["palabras"][termino] = {
            "termino": termino, "traduccion": traduccion, "frase": frase, "nivel": nivel,
            "es_frase": es_frase, "veces": (previa["veces"] + 1) if previa else 1,
        }
        return True

    async def tocar_palabra(palabra, frase, nivel):
        """Hoja inferior con la traducción de la palabra en el contexto de su frase."""
        termino = palabra.lower()
        cuerpo = ft.Column(tight=True, spacing=12, width=ancho())

        def cerrar(e):
            page.pop_dialog()

        def cargando(mensaje):
            return ft.Row(
                [ft.ProgressRing(color=AMBAR, width=22, height=22), txt(mensaje, color=APAGADO)],
                spacing=12,
            )

        def pintar(res, guardado, frase_es=None):
            controles = [
                ft.Row(
                    [txt(palabra, size=26, weight=ft.FontWeight.BOLD, color=AMBAR),
                     txt(res.get("tipo", ""), size=13, color=APAGADO)],
                    spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                txt(res["traduccion"], size=22),
                txt(f"“{frase}”", size=14, color=APAGADO, italic=True),
            ]
            if frase_es:
                controles.append(tarjeta(txt(frase_es, size=15), padding=12, bgcolor=SUPERFICIE_2))
            controles.append(
                ft.Row(
                    [ft.Icon(ft.Icons.CHECK_CIRCLE if guardado else ft.Icons.ERROR_OUTLINE,
                             color=TURQUESA if guardado else ERROR, size=16),
                     txt("Guardada para tu test de vocabulario" if guardado
                         else "No se pudo guardar esta palabra",
                         size=12, color=APAGADO)],
                    spacing=6,
                )
            )
            botones = []
            if not frase_es:
                botones.append(ft.TextButton(content=ft.Text("Traducir la frase", color=AZUL),
                                             on_click=ver_frase))
            botones.append(ft.TextButton(content=ft.Text("Cerrar", color=APAGADO), on_click=cerrar))
            controles.append(ft.Row(botones, alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            cuerpo.controls = controles
            page.update()

        estado = {"res": None, "guardado": False}

        async def ver_frase(e):
            cuerpo.controls = [cargando("Traduciendo la frase...")]
            page.update()
            frase_es = sesion["cache_frases"].get(frase)
            if frase_es is None:
                frase_es = await asyncio.to_thread(ia.traducir_frase, frase)
                if frase_es:
                    sesion["cache_frases"][frase] = frase_es
            if frase_es:
                # La frase completa también cuenta como "frase tocada" para el test.
                await guardar_termino(frase.lower(), frase_es, frase, nivel, es_frase=True)
            pintar(estado["res"], estado["guardado"], frase_es)

        cuerpo.controls = [cargando(f"Traduciendo “{palabra}”...")]
        page.show_dialog(
            ft.BottomSheet(content=ft.Container(content=cuerpo, padding=24, bgcolor=SUPERFICIE))
        )

        res = sesion["cache_trad"].get((termino, frase))
        if res is None:
            res = await asyncio.to_thread(ia.traducir_en_contexto, palabra, frase)
            if res:
                sesion["cache_trad"][(termino, frase)] = res
        if not res:
            cuerpo.controls = [
                txt(palabra, size=26, weight=ft.FontWeight.BOLD, color=AMBAR),
                txt("No se pudo traducir. Toca la palabra para intentarlo de nuevo.", color=ERROR),
                ft.TextButton(content=ft.Text("Cerrar", color=APAGADO), on_click=cerrar),
            ]
            page.update()
            return

        guardado = await guardar_termino(termino, res["traduccion"], frase, nivel)
        estado["res"], estado["guardado"] = res, guardado
        pintar(res, guardado)

    def hacer_click(palabra, frase, nivel):
        async def al_tocar(e):
            await tocar_palabra(palabra, frase, nivel)
        return al_tocar

    def construir_parrafo(parrafo, nivel):
        """Convierte un párrafo (con **negritas**) en un texto donde cada palabra se puede tocar."""
        plano, negrita = [], []
        for i, trozo in enumerate(parrafo.split("**")):
            plano.append(trozo)
            negrita.extend([i % 2 == 1] * len(trozo))
        plano = "".join(plano)

        frases = [(m.start(), m.end()) for m in _FRASES.finditer(plano)]

        def estilo(es_negrita, guardada=False):
            return ft.TextStyle(
                size=17, height=1.55,
                color=AMBAR if es_negrita else TEXTO,
                weight=ft.FontWeight.BOLD if es_negrita else None,
                decoration=ft.TextDecoration.UNDERLINE if guardada else None,
                decoration_color=TURQUESA if guardada else None,
            )

        spans, pos = [], 0
        for m in _PALABRAS.finditer(plano):
            if m.start() > pos:
                spans.append(ft.TextSpan(text=plano[pos:m.start()], style=estilo(negrita[pos])))
            ini, fin = next(((a, b) for a, b in frases if a <= m.start() < b), (0, len(plano)))
            frase = plano[ini:fin].strip()
            palabra = m.group()
            spans.append(
                ft.TextSpan(
                    text=palabra,
                    style=estilo(negrita[m.start()], palabra.lower() in sesion["palabras"]),
                    on_click=hacer_click(palabra, frase, nivel),
                )
            )
            pos = m.end()
        if pos < len(plano):
            spans.append(ft.TextSpan(text=plano[pos:], style=estilo(negrita[pos])))
        return ft.Text(spans=spans, size=17)

    def vista_lectura(contenido, acciones, volver=None, nivel=None):
        estilo_md = ft.MarkdownStyleSheet(
            p_text_style=ft.TextStyle(size=17, height=1.55, color=TEXTO),
            strong_text_style=ft.TextStyle(size=17, color=AMBAR, weight=ft.FontWeight.BOLD),
        )
        parrafos = [p.strip() for p in re.split(r"\n\s*\n", contenido["texto"].strip()) if p.strip()]
        texto_en = [construir_parrafo(p, nivel) for p in parrafos]
        zona = ft.Column(texto_en, spacing=14)
        vista = {"español": False}

        async def alternar_idioma(e):
            clave = contenido["titulo"]
            if vista["español"]:
                vista["español"] = False
                btn_idioma.content.value = "Ver en español"
                zona.controls = texto_en
                page.update()
                return

            vista["español"] = True
            btn_idioma.content.value = "Ver en inglés"
            if clave not in sesion["cache_es"]:
                zona.controls = [
                    ft.Row([ft.ProgressRing(color=AMBAR, width=22, height=22),
                            txt("Traduciendo la historia...", color=APAGADO)], spacing=12)
                ]
                page.update()
                traduccion = await asyncio.to_thread(ia.traducir_texto, contenido["texto"])
                if not traduccion:
                    vista["español"] = False
                    btn_idioma.content.value = "Ver en español"
                    zona.controls = texto_en
                    page.update()
                    return
                sesion["cache_es"][clave] = traduccion
            zona.controls = [
                ft.Markdown(sesion["cache_es"][clave], extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            md_style_sheet=estilo_md)
            ]
            page.update()

        btn_idioma = boton("Ver en español", alternar_idioma, primario=False)

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
        partes.append(txt("Toca cualquier palabra para ver su significado en esa frase.",
                          size=13, color=APAGADO))
        partes.append(btn_idioma)
        partes.append(zona)
        partes.extend(acciones)
        mostrar(*partes)

    def mostrar_tema_guardado(tema, volver):
        vista_lectura(tema, [boton("Volver", lambda e: volver(), primario=False)],
                      volver=volver, nivel=tema.get("nivel"))

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

    def mostrar_palabras():
        lista = sorted(sesion["palabras"].values(), key=lambda p: (-p["veces"], p["termino"]))
        tarjetas = []
        for p in lista:
            detalle = [
                txt(p["termino"], size=17, weight=ft.FontWeight.BOLD, color=AMBAR),
                txt(p["traduccion"], size=15),
            ]
            if p.get("frase") and not p.get("es_frase"):
                detalle.append(txt(f"“{p['frase']}”", size=12, color=APAGADO, italic=True))
            if p["veces"] > 1:
                detalle.append(txt(f"Consultada {p['veces']} veces", size=12, color=APAGADO))
            tarjetas.append(tarjeta(ft.Column(detalle, spacing=3), width=ancho()))
        mostrar(
            barra_volver(mostrar_mapa),
            txt("Mis palabras", size=28, weight=ft.FontWeight.BOLD),
            txt(f"{len(lista)} guardadas", size=13, color=APAGADO),
            *tarjetas,
        )

    # ── Aprendizaje ─────────────────────────────────────────────────────────
    async def iniciar_aprendizaje(e=None):
        if sesion["cargando"]:  # doble toque mientras se carga/genera
            return
        sesion["cargando"] = True
        try:
            nivel = sesion["nivel"]

            # 1) ¿Ya se generó la historia de este nivel? Se reutiliza tal cual.
            contenido = None
            if sesion.get("contenido") and sesion.get("contenido_nivel") == nivel:
                contenido = sesion["contenido"]
            else:
                mostrar_cargando("Abriendo tu historia...")
                try:
                    contenido = await asyncio.to_thread(db.cargar_pendiente, sesion["usuario"], nivel)
                except Exception as ex:
                    print(f"No se pudo leer la historia pendiente: {ex}")

            # 2) Si no existe, se genera y se guarda al momento.
            if not contenido:
                mostrar_cargando("Buscando una historia que no conoces...")
                titulos = [t["titulo"] for t in sesion["temas"]]
                contenido = await asyncio.to_thread(ia.generar_microaprendizaje, nivel, titulos)
                if not contenido.get("error"):
                    try:
                        await asyncio.to_thread(
                            db.guardar_pendiente, sesion["usuario"], nivel, contenido["titulo"],
                            contenido["texto"], contenido.get("imagen_url"), contenido.get("categoria"),
                        )
                    except Exception as ex:
                        print(f"No se pudo guardar la historia pendiente: {ex}")

            if contenido.get("error"):
                pantalla_error(contenido["titulo"], iniciar_aprendizaje, contenido["texto"])
                return

            sesion["contenido"] = contenido
            sesion["contenido_nivel"] = nivel
            vista_lectura(
                contenido,
                [ft.Container(height=8), boton("Terminar y ganar una estrella", completar_nivel)],
                volver=mostrar_mapa,
                nivel=nivel,
            )
        finally:
            sesion["cargando"] = False

    async def completar_nivel(e):
        if sesion["completando"]:  # doble toque: ya se está guardando
            return

        c = sesion.get("contenido")
        nivel_completado = sesion.get("contenido_nivel")
        # Si este nivel ya se completó (o no hay historia abierta), no se vuelve a contar.
        if not c or nivel_completado != sesion["nivel"]:
            mostrar_mapa()
            return

        sesion["completando"] = True
        try:
            mostrar_cargando("Guardando tu progreso...")
            try:
                nuevo_nivel, estrellas = await asyncio.to_thread(
                    db.guardar_tema_y_progreso, sesion["usuario"], nivel_completado,
                    c["titulo"], c["texto"], c.get("imagen_url"),
                )
            except Exception as ex:
                pantalla_error("No se pudo guardar el progreso", completar_nivel, str(ex))
                return

            sesion["temas"].append(
                {"titulo": c["titulo"], "texto": c["texto"], "imagen_url": c.get("imagen_url"),
                 "nivel": nivel_completado}
            )
            sesion.update(nivel=nuevo_nivel, estrellas=estrellas, contenido=None, contenido_nivel=None)

            mostrar(
                ft.Container(height=60),
                ft.Icon(ft.Icons.STAR, color=AMBAR, size=110),
                txt("Nivel completado", size=30, weight=ft.FontWeight.BOLD, align=ft.TextAlign.CENTER),
                txt(f"Has ganado una estrella. El nivel {nuevo_nivel} ya está disponible.",
                    color=APAGADO, align=ft.TextAlign.CENTER),
                ft.Container(height=10),
                boton("Volver al mapa", lambda e: mostrar_mapa()),
            )
        finally:
            sesion["completando"] = False

    # ── Examen de historias (acumulativo) ───────────────────────────────────
    async def iniciar_examen(e=None):
        mostrar_cargando("Preparando tu examen...")
        # Se pasan TODAS las historias; el servicio elige una muestra aleatoria distinta cada vez.
        quiz = await asyncio.to_thread(ia.generar_quiz, list(sesion["temas"]))
        preguntas = quiz.get("preguntas", [])

        if not preguntas:
            pantalla_error("No se pudo generar el examen", iniciar_examen)
            return

        entradas = []  # (pregunta, función que devuelve la respuesta)
        tarjetas = []
        for idx, p in enumerate(preguntas, start=1):
            tipo = p.get("tipo", "")
            if tipo in ("opcion_multiple", "verdadero_falso"):
                opciones = p.get("opciones") or ["Verdadero", "Falso"]
                grupo = ft.RadioGroup(content=ft.Column([]))

                def fila_opcion(o, g=grupo):
                    # El texto va aparte del Radio para que salte de línea en vez de cortarse por la derecha.
                    def elegir(e, o=o, g=g):
                        g.value = o
                        g.update()
                    return ft.Row(
                        [ft.Radio(value=o),
                         ft.Container(txt(o, size=15), expand=True, on_click=elegir, padding=ft.padding.only(top=10))],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=4,
                    )

                grupo.content = ft.Column([fila_opcion(o) for o in opciones], spacing=2)
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
            dadas = [(leer() or "").strip() for _, leer in entradas]  # se leen antes de cambiar de pantalla
            mostrar_cargando("Corrigiendo tus respuestas...")

            # Las preguntas de escribir (completar y redactar) las corrige la IA; el resto, por coincidencia.
            abiertas = [
                {"tipo": p.get("tipo"), "pregunta": p["pregunta"],
                 "referencia": p.get("respuesta_correcta", ""), "respuesta": d}
                for (p, _), d in zip(entradas, dadas)
                if p.get("tipo") in ("completar", "redactar") and d
            ]
            evaluaciones = await asyncio.to_thread(ia.corregir_respuestas_examen, abiertas) if abiertas else []
            siguiente = iter(evaluaciones) if evaluaciones is not None else None

            resultados, aciertos, total = [], 0, len(entradas)
            for (p, _), dada in zip(entradas, dadas):
                correcta = p.get("respuesta_correcta", "")
                comentario = ""
                if p.get("tipo") in ("completar", "redactar"):
                    if not dada:
                        estado = False
                    elif siguiente is not None:
                        ev = next(siguiente)
                        estado, comentario = ev["correcta"], ev["comentario"]
                    elif p.get("tipo") == "completar":
                        # Sin IA: se compara el texto.
                        estado = normalizar(dada) == normalizar(correcta)
                    else:
                        estado = None  # redactar sin IA: se autoevalúa
                        comentario = "No se pudo corregir automáticamente: compárala con la referencia."
                else:
                    estado = normalizar(dada) == normalizar(correcta)
                if estado is True:
                    aciertos += 1
                resultados.append((p, dada, correcta, estado, comentario))

            aviso = ""
            try:
                await asyncio.to_thread(db.guardar_examen, sesion["usuario"], aciertos, total, "historias")
            except Exception as ex:
                aviso = f"No se pudo guardar el resultado: {ex}"

            filas = []
            for p, dada, correcta, estado, comentario in resultados:
                icono, color = (
                    (ft.Icons.CHECK_CIRCLE, TURQUESA) if estado is True
                    else (ft.Icons.CANCEL, ERROR) if estado is False
                    else (ft.Icons.EDIT_NOTE, AMBAR)
                )
                detalle = [txt(p["pregunta"], weight=ft.FontWeight.BOLD, size=15)]
                if estado is not True:
                    detalle.append(txt(f"Tu respuesta: {dada or '(en blanco)'}", size=14, color=APAGADO))
                    detalle.append(txt(f"Respuesta de referencia: {correcta}", size=14, color=TEXTO))
                if comentario:
                    detalle.append(txt(comentario, size=13, color=APAGADO))
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
                         txt("respuestas correctas", color=APAGADO)],
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
            txt("Examen de historias", size=28, weight=ft.FontWeight.BOLD),
            txt(f"Preguntas sobre tus {len(sesion['temas'])} historias.", size=13, color=APAGADO),
            *tarjetas,
            boton("Corregir", corregir),
        )

    # ── Test de vocabulario ─────────────────────────────────────────────────
    async def iniciar_test_vocabulario(e=None):
        mostrar_cargando("Preparando tu test de vocabulario...")
        try:
            palabras = await asyncio.to_thread(db.listar_palabras, sesion["usuario"])
        except Exception as ex:
            pantalla_error("No se pudieron cargar tus palabras", iniciar_test_vocabulario, str(ex))
            return
        if len(palabras) < MIN_PALABRAS:
            pantalla_error(
                "Aún no hay suficientes palabras", iniciar_test_vocabulario,
                f"Toca palabras mientras lees. Necesitas al menos {MIN_PALABRAS}.",
            )
            return

        test = await asyncio.to_thread(ia.generar_test_vocabulario, palabras)
        preguntas = test.get("preguntas", [])
        if not preguntas:
            pantalla_error("No se pudo generar el test", iniciar_test_vocabulario)
            return

        campos, tarjetas = [], []
        for idx, p in enumerate(preguntas, start=1):
            al_ingles = p.get("direccion") == "es_en"
            campo = ft.TextField(
                hint_text="Tradúcela al inglés" if al_ingles else "Tradúcela al español",
                bgcolor=TINTA, border_color=SUPERFICIE_2,
                focused_border_color=AMBAR, border_radius=12, multiline=True, min_lines=2,
            )
            campos.append(campo)
            tarjetas.append(
                tarjeta(
                    ft.Column(
                        [txt(f"{idx}. Traduce al inglés" if al_ingles else f"{idx}. Traduce al español", size=13, color=APAGADO),
                         txt(p["frase"], size=17, weight=ft.FontWeight.BOLD),
                         campo],
                        spacing=10,
                    )
                )
            )

        async def corregir(e):
            respuestas = [(c.value or "").strip() for c in campos]  # se leen antes de cambiar de pantalla
            mostrar_cargando("Corrigiendo tus traducciones...")

            # Las respuestas en blanco son fallo directo; el resto las corrige la IA.
            a_corregir = [
                {"termino": p.get("termino", ""), "frase": p["frase"],
                 "referencia": p["traduccion_referencia"], "respuesta": r,
                 "direccion": p.get("direccion", "en_es")}
                for p, r in zip(preguntas, respuestas) if r
            ]
            evaluaciones = await asyncio.to_thread(ia.corregir_traducciones, a_corregir)
            if evaluaciones is None:
                # Sin IA: acierto si coincide con la referencia; si no, se autoevalúa.
                evaluaciones = [
                    {"correcta": True if normalizar(it["respuesta"]) == normalizar(it["referencia"]) else None,
                     "comentario": "" if normalizar(it["respuesta"]) == normalizar(it["referencia"])
                     else "No se pudo corregir automáticamente: compárala con la referencia."}
                    for it in a_corregir
                ]
            siguiente = iter(evaluaciones)

            resultados, aciertos = [], 0
            for p, r in zip(preguntas, respuestas):
                ev = next(siguiente) if r else {"correcta": False, "comentario": ""}
                aciertos += 1 if ev["correcta"] is True else 0
                resultados.append((p, r, ev))

            aviso = ""
            try:
                await asyncio.to_thread(
                    db.guardar_examen, sesion["usuario"], aciertos, len(preguntas), "vocabulario"
                )
            except Exception as ex:
                aviso = f"No se pudo guardar el resultado: {ex}"

            filas = []
            for p, r, ev in resultados:
                icono, color = (
                    (ft.Icons.CHECK_CIRCLE, TURQUESA) if ev["correcta"] is True
                    else (ft.Icons.CANCEL, ERROR) if ev["correcta"] is False
                    else (ft.Icons.EDIT_NOTE, AMBAR)
                )
                detalle = [txt(p["frase"], weight=ft.FontWeight.BOLD, size=15)]
                if ev["correcta"] is not True:
                    detalle.append(txt(f"Tu traducción: {r or '(en blanco)'}", size=14, color=APAGADO))
                detalle.append(txt(f"Referencia: {p['traduccion_referencia']}", size=14))
                if p.get("termino"):
                    detalle.append(txt(f"Palabras trabajadas: {p['termino']}", size=12, color=AZUL))
                if ev["comentario"]:
                    detalle.append(txt(ev["comentario"], size=13, color=APAGADO))
                filas.append(
                    tarjeta(ft.Row([ft.Icon(icono, color=color, size=28),
                                    ft.Column(detalle, spacing=4, expand=True)],
                                   vertical_alignment=ft.CrossAxisAlignment.START, spacing=12))
                )

            mostrar(
                txt("Resultado", size=28, weight=ft.FontWeight.BOLD),
                tarjeta(
                    ft.Column(
                        [txt(f"{aciertos} de {len(preguntas)}", size=44, weight=ft.FontWeight.BOLD, color=AMBAR),
                         txt("traducciones correctas", color=APAGADO)],
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
            txt("Test de vocabulario", size=28, weight=ft.FontWeight.BOLD),
            txt("5 frases con palabras que has tocado: 2 al español y 3 al inglés.", size=13, color=APAGADO),
            *tarjetas,
            boton("Corregir", corregir),
        )

    try:
        await asyncio.to_thread(db.init_db)
    except Exception as ex:
        mostrar_login(f"No se pudo preparar la base de datos: {ex}")
        return

    guardado = await leer_pref(CLAVE_NOMBRE)
    if guardado:
        await iniciar_sesion(guardado)
    else:
        mostrar_login()


if __name__ == "__main__":
    ft.run(main, view=None, port=int(os.environ.get("PORT", 8080)))
