import flet as ft
import gemini_service as ia
import os

# Almacenamiento simple en memoria
estado = {
    "nivel_actual": 1,
    "temas_aprendidos": [],
    "estrellas": 0,
    "contenido_actual": None
}

def main(page: ft.Page):
    page.title = "Cultura General App"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.bgcolor = "#1a1a1a"

    def mostrar_mapa():
        page.controls.clear()

        header = ft.Row([
            ft.Text(f"⭐ {estado['estrellas']}", size=20, color="yellow"),
            ft.Text(f"Nivel {estado['nivel_actual']}", size=20, color="white")
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        nodos = []
        for i in range(1, 6):
            if i < estado['nivel_actual']:
                icono = ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=40)
                bgcolor = "#2e2e2e"
                on_click = None
            elif i == estado['nivel_actual']:
                icono = ft.Icon(ft.Icons.PLAY_ARROW, color="black", size=40)
                bgcolor = "yellow"
                on_click = lambda e: iniciar_aprendizaje()
            else:
                icono = ft.Icon(ft.Icons.LOCK, color="grey", size=30)
                bgcolor = "#2e2e2e"
                on_click = None

            nodo = ft.Container(
                content=icono,
                width=80, height=80,
                bgcolor=bgcolor,
                border_radius=40,
                alignment=ft.Alignment.CENTER,
                on_click=on_click,
                ink=True
            )

            if i < 5:
                # Usamos Padding en lugar de Margin para el conector (más seguro en Flet 1.0)
                conector = ft.Container(
                    content=ft.Icon(ft.Icons.SOUTH, color="#555555", size=30),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(0, 10, 0, 10)
                )
                nodos.append(nodo)
                nodos.append(conector)
            else:
                nodos.append(nodo)

        btn_examen = None
        if len(estado['temas_aprendidos']) >= 5:
            btn_examen = ft.Button(
                "Hacer Examen de Repaso",
                bgcolor="purple",
                color="white",
                on_click=lambda e: iniciar_examen()
            )

        page.add(
            header,
            ft.Column(
                nodos,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                scroll=ft.ScrollMode.AUTO,
                expand=True # Para que ocupe el espacio y permita scroll en móvil
            ),
            btn_examen if btn_examen else ft.Container()
        )
        page.update()

    def iniciar_aprendizaje():
        page.controls.clear()
        page.add(
            ft.Column([
                ft.ProgressRing(),
                ft.Text("Generando conocimiento...", color="white")
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        )
        page.update()

        # Llamada a la IA
        contenido = ia.generar_microaprendizaje(estado['nivel_actual'])
        estado['contenido_actual'] = contenido

        page.controls.clear()

        img_control = None
        if contenido.get("imagen_url"):
            img_control = ft.Image(
                src=contenido["imagen_url"],
                width=300, height=200,
                fit=ft.ImageFit.COVER,
                border_radius=10
            )

        page.add(
            ft.Column([
                ft.Text(contenido["titulo"], size=24, weight=ft.FontWeight.BOLD, color="white"),
                img_control if img_control else ft.Container(),
                ft.Text(contenido["texto"], size=16, color="white"),
                ft.Container(height=20), # Espaciador
                ft.Button(
                    content=ft.Text("Finalizar Aprendizaje", color="black", weight=ft.FontWeight.BOLD),
                    bgcolor="yellow",
                    on_click=lambda e: completar_nivel(contenido["titulo"])
                )
            ], scroll=ft.ScrollMode.AUTO, expand=True)
        )
        page.update()

    def completar_nivel(titulo):
        estado['temas_aprendidos'].append(titulo)
        estado['estrellas'] += 1
        estado['nivel_actual'] += 1

        page.controls.clear()
        page.add(
            ft.Column([
                ft.Icon(ft.Icons.STAR, color="yellow", size=100),
                ft.Text("¡Nivel Completado!", size=30, color="white", weight=ft.FontWeight.BOLD),
                ft.Text(f"Has ganado 1 estrella. Nivel {estado['nivel_actual']} desbloqueado.", color="grey"),
                ft.Container(height=20),
                ft.Button("Volver al Mapa", on_click=lambda e: mostrar_mapa())
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        )
        page.update()

    def iniciar_examen():
        page.controls.clear()
        page.add(
            ft.Column([
                ft.ProgressRing(),
                ft.Text("Generando examen...", color="white")
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        )
        page.update()

        quiz_data = ia.generar_quiz(estado['temas_aprendidos'])

        page.controls.clear()
        
        controles_examen = [ft.Text("Examen de Repaso", size=24, weight=ft.FontWeight.BOLD, color="white")]
        
        for idx, p in enumerate(quiz_data.get("preguntas", [])):
            controles_examen.append(ft.Text(f"{idx+1}. {p['pregunta']}", color="white", weight=ft.FontWeight.BOLD))
            controles_examen.append(ft.TextField(hint_text="Tu respuesta...", width=300))
            controles_examen.append(ft.Container(height=10))

        controles_examen.append(ft.Button("Volver al Mapa", on_click=lambda e: mostrar_mapa()))

        page.add(
            ft.Column(controles_examen, scroll=ft.ScrollMode.AUTO, expand=True)
        )
        page.update()

    mostrar_mapa()

# Ejecución adaptada a Flet 1.0
if __name__ == "__main__":
    ft.run(main, view=None, port=int(os.environ.get("PORT", 8080)))