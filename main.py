from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Iniciando Chromium headless con Playwright...")
    nfts_capturados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        page = await context.new_page()

        # Interceptar todas las respuestas de red para capturar el JSON con los datos
        async def interceptar_respuestas(response):
            nonlocal nfts_capturados
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = await response.json()
                    items = None
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = (
                            data.get("data") or 
                            data.get("items") or 
                            data.get("lists") or 
                            data.get("nfts") or 
                            data.get("results")
                        )
                        if isinstance(items, dict):
                            items = items.get("lists") or items.get("items") or items.get("data")

                    if isinstance(items, list) and len(items) > 0:
                        nfts_capturados = items
                        print(f"🎯 Capturado JSON de red con {len(items)} items")
            except Exception:
                pass

        page.on("response", interceptar_respuestas)

        try:
            url_objetivo = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            print(f"🌐 Navegando a {url_objetivo}...")
            
            await page.goto(url_objetivo, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(3)

            if nfts_capturados:
                BASE_DE_DATOS_NFTS = nfts_capturados
                DIAGNOSTICO_ESTADO = f"✅ Éxito total: {len(nfts_capturados)} personajes capturados mediante Playwright."
            else:
                # Intento secundario: evaluar si el objeto existe en memoria del navegador
                estado_window = await page.evaluate("""() => {
                    if (window.__NEXT_DATA__) return window.__NEXT_DATA__;
                    if (window.__INITIAL_STATE__) return window.__INITIAL_STATE__;
                    return null;
                }""")
                
                if estado_window:
                    DIAGNOSTICO_ESTADO = "Renderizado completado, pero los datos requieren formateo del objeto de ventana."
                else:
                    DIAGNOSTICO_ESTADO = "Página cargada con éxito, pero no se emitieron peticiones JSON reconocibles en la red."

        except Exception as e:
            DIAGNOSTICO_ESTADO = f"Error en ejecución de Playwright: {str(e)}"
        finally:
            await browser.close()

async def planificador_background():
    while True:
        await obtener_nfts_con_playwright()
        await asyncio.sleep(900)  # Ejecutar cada 15 minutos

@app.on_event("startup")
async def al_iniciar():
    asyncio.create_task(planificador_background())

@app.get("/api/nfts")
async def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
