from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import json
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "🔄 Iniciando Chromium en Render..."
    nfts_encontrados = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )

            page = await context.new_page()

            # 1. Interceptor de red de respaldo (por si acaso)
            async def interceptar_respuestas(response):
                nonlocal nfts_encontrados
                try:
                    if "application/json" in response.headers.get("content-type", ""):
                        data = await response.json()
                        items = data if isinstance(data, list) else (
                            data.get("data") or data.get("items") or data.get("lists") or data.get("nfts")
                        )
                        if isinstance(items, list) and len(items) > 0:
                            nfts_encontrados = items
                except Exception:
                    pass

            page.on("response", interceptar_respuestas)

            url_objetivo = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            DIAGNOSTICO_ESTADO = f"🌐 Cargando {url_objetivo}..."
            
            await page.goto(url_objetivo, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(4)  # Esperar a que el DOM se asiente

            # 2. Extracción directa del HTML procesado por el navegador
            if not nfts_encontrados:
                DIAGNOSTICO_ESTADO = "🔍 Extrayendo datos directly del DOM (__NEXT_DATA__)..."
                
                # Extraer la etiqueta __NEXT_DATA__
                next_data_raw = await page.evaluate("""() => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? el.textContent : null;
                }""")

                if next_data_raw:
                    try:
                        payload = json.loads(next_data_raw)
                        page_props = payload.get("props", {}).get("pageProps", {})

                        # Buscar arreglos en pageProps
                        def buscar_listas(obj):
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                                        return v
                                    res = buscar_listas(v)
                                    if res: return res
                            elif isinstance(obj, list):
                                for elem in obj:
                                    res = buscar_listas(elem)
                                    if res: return res
                            return None

                        extracted = buscar_listas(page_props)
                        if extracted:
                            nfts_encontrados = extracted
                    except Exception as e:
                        print(f"Error parseando __NEXT_DATA__: {e}")

            # 3. Resultado final
            if nfts_encontrados:
                BASE_DE_DATOS_NFTS = nfts_encontrados
                DIAGNOSTICO_ESTADO = f"✅ Éxito total: {len(nfts_encontrados)} personajes cargados desde HofGamer."
            else:
                DIAGNOSTICO_ESTADO = "⚠️ No se encontraron listas de personajes en la página."

            await browser.close()

    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error en Playwright: {str(e)}"

async def planificador_background():
    while True:
        await obtener_nfts_con_playwright()
        await asyncio.sleep(900)

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
