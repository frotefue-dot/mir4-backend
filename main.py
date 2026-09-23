from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "🔄 Iniciando navegador Chromium en Render..."
    print("🔄 Iniciando Chromium headless con Playwright...")
    nfts_capturados = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )

            page = await context.new_page()

            # Intercepción de red para capturar respuestas JSON de HofGamer
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
                            print(f"🎯 Capturado JSON con {len(items)} items")
                except Exception:
                    pass

            page.on("response", interceptar_respuestas)

            url_objetivo = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            DIAGNOSTICO_ESTADO = f"🌐 Cargando {url_objetivo}..."
            
            # Carga rápida sin bloquearse por peticiones secundarias
            await page.goto(url_objetivo, wait_until="domcontentloaded", timeout=45000)
            
            DIAGNOSTICO_ESTADO = "⏳ Esperando a que el JavaScript de la página ejecute las llamadas API..."
            await asyncio.sleep(6)  # Tiempo para que React/Next.js cargue los componentes

            if nfts_capturados:
                BASE_DE_DATOS_NFTS = nfts_capturados
                DIAGNOSTICO_ESTADO = f"✅ Éxito total: {len(nfts_capturados)} personajes cargados desde HofGamer."
            else:
                DIAGNOSTICO_ESTADO = "⚠️ Página cargada correctamente, pero no se detectaron respuestas JSON en el tráfico de red."

            await browser.close()

    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error durante la ejecución de Playwright: {str(e)}"
        print(f"Error: {e}")

async def planificador_background():
    while True:
        await obtener_nfts_con_playwright()
        await asyncio.sleep(900)  # Actualizar cada 15 minutos

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(planificador_background())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/nfts")
async def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
