import flet as ft
import gemini_service as ia
import json
import os

# Almacenamiento simple en memoria (para producción usa una BD como SQLite)
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
    page.bgcolor = "#1a1a1a"  # Fondo oscuro tipo Gen K

    # --- FUNCIONES DE NAVEGACIÓN ---
    
    def mostrar_mapa():
        page.controls.clear()
        
        # Cabecera con estrellas
        header = ft.Row([
            ft.Text(f"⭐ {estado['estrellas']}", size=20, color="yellow"),
            ft.Text(f"Nivel {estado['nivel_actual']}", size=20, color="white")
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        
        # Simulación del camino (Nodos)
        nodos = []
        for i in range(1, 6):
            if i < estado['nivel_actual']:
                # Nivel completado
                icono = ft.Icon(ft.icons.CHECK_CIRCLE, color="green", size=40)
                bgcolor = "#2e2e2e"
                on_click = None
            elif i == estado['nivel_actual']:
                # Nivel actual (Desbloqueado)
                icono = ft.Icon(ft.icons.PLAY_ARROW, color="black", size=40)
                bgcolor = "yellow"
                on_click = lambda e: iniciar_aprendizaje()
            else:
                # Bloqueado
                icono = ft.Icon(ft.icons.LOCK, color="grey", size=30)
                bgcolor = "#2e2e2e"
                on_click = None
            
            nodo = ft.Container(
                content=icono,
                width=80, height=80,
                bgcolor=bgcolor,
                border_radius=40,
                alignment=ft.alignment.center,
                on_click=on_click,
                ink=True
            )
            
            # Conector curvado simulado con un contenedor
            if i < 5:
                conector = ft.Container(
                    content=ft.Icon(ft.icons.SOUTH, color="#555555", size=30),
                    alignment=ft.alignment.center,
                    margin=ft.margin.only(top=10, bottom=10)
                )
                nodos.append(nodo)
                nodos.append(conector)
            else:
                nodos.append(nodo)
        
        # Botón de Examen (solo si hay 5 temas)
        btn_examen = None
        if len(estado['temas_aprendidos']) >= 5:
            btn_examen = ft.ElevatedButton(
                "Hacer Examen de Repaso",
                bgcolor="purple",
                color="white",
                on_click=lambda e: iniciar_examen()
            )
            
        page.add(
            header,
            ft.Column(nodos, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
            btn_examen if btn_examen else ft.Container()
        )
        page.update()

    def iniciar_aprendizaje():
        page.controls.clear()
        
        # Pantalla de carga
        page.add(ft.ProgressRing(), ft.Text("Generando conocimiento...", color="white"))
        page.update()
        
        # Llamada a la IA
        contenido = ia.generar_microaprendizaje(estado['nivel_actual'])
        estado['contenido_actual'] = contenido
        
        # Pantalla de contenido
        page.controls.clear()
        
        # Imagen (si existe)
        img_control = None
        if contenido.get("imagen_url"):
            img_control = ft.Image(src=contenido["imagen_url"], width=300, height=200, fit=ft.ImageFit.COVER, border_radius=10)
        
        page.add(
            ft.Text(contenido["titulo"], size=24, weight="bold", color="white"),
            img_control if img_control else ft.Container(),
            ft.Text(contenido["texto"], size=16, color="white"),
            ft.ElevatedButton(
                "Finalizar Aprendizaje",
                bgcolor="yellow",
                color="black",
                on_click=lambda e: completar_nivel(contenido["titulo"])
            )
        )
        page.update()

    def completar_nivel(titulo):
        # Guardamos el tema
        estado['temas_aprendidos'].append(titulo)
        estado['estrellas'] += 1
        estado['nivel_actual'] += 1
        
        # Pantalla de recompensa (simulada)
        page.controls.clear()
        page.add(
            ft.Icon(ft.icons.STAR, color="yellow", size=100),
            ft.Text("¡Nivel Completado!", size=30, color="white"),
            ft.Text(f"Has ganado 1 estrella. Nivel {estado['nivel_actual']} desbloqueado.", color="grey"),
            ft.ElevatedButton("Volver al Mapa", on_click=lambda e: mostrar_mapa())
        )
        page.update()

    def iniciar_examen():
        page.controls.clear()
        page.add(ft.ProgressRing(), ft.Text("Generando examen...", color="white"))
        page.update()
        
        # Llamada a la IA para el quiz
        quiz_data = ia.generar_quiz(estado['temas_aprendidos'])
        
        page.controls.clear()
        page.add(ft.Text("Examen de Repaso", size=24, weight="bold", color="white"))
        
        # Renderizar preguntas (simplificado, solo mostramos el texto)
        for idx, p in enumerate(quiz_data.get("preguntas", [])):
            page.add(ft.Text(f"{idx+1}. {p['pregunta']}", color="white"))
            # Aquí iría la lógica de input según el tipo (test, texto, etc.)
            page.add(ft.TextField(hint_text="Tu respuesta...", width=300))
        
        page.add(ft.ElevatedButton("Volver al Mapa", on_click=lambda e: mostrar_mapa()))
        page.update()

    # Iniciar app
    mostrar_mapa()

ft.app(target=main, view=None, port=int(os.environ.get("PORT", 8080)))