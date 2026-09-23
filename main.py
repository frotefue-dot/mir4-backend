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
    DIAGNOSTICO_ESTADO = "🔄 Abriendo Chromium en Render..."
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
                viewport={"width": 1400, "height": 900}
            )

            page = await context.new_page()

            # 1. Interceptar respuestas JSON por si se emiten en red
            async def interceptar_respuestas(response):
                nonlocal nfts_capturados
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct or "graphql" in response.url:
                        data = await response.json()
                        items = None
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            items = (
                                data.get("data", {}).get("nfts") or 
                                data.get("data", {}).get("items") or 
                                data.get("data", {}).get("lists") or 
                                data.get("items") or 
                                data.get("nfts")
                            )
                        if isinstance(items, list) and len(items) > 0:
                            nfts_capturados = items
                except Exception:
                    pass

            page.on("response", interceptar_respuestas)

            url_target = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            DIAGNOSTICO_ESTADO = f"🌐 Cargando {url_target}..."
            await page.goto(url_target, wait_until="domcontentloaded", timeout=60000)

            DIAGNOSTICO_ESTADO = "⏳ Esperando renderizado de elementos en pantalla..."
            
            # Esperar a que cargue la lista o elementos visibles en la interfaz
            try:
                await page.wait_for_selector("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']", timeout=15000)
            except Exception:
                await asyncio.sleep(5)

            # 2. Si la intercepción de red no atrapó datos, extraer directamente del DOM de la página
            if not nfts_capturados:
                DIAGNOSTICO_ESTADO = "🔍 Extrayendo tarjetas de personajes desde el DOM..."
                
                # Scraping directo en el navegador de los elementos visuales
                dom_items = await page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']"));
                    return cards.map((c, idx) => {
                        const text = c.innerText || "";
                        const img = c.querySelector("img") ? c.querySelector("img").src : "";
                        const link = c.tagName === "A" ? c.href : (c.querySelector("a") ? c.querySelector("a").href : "");
                        return {
                            id: idx + 1,
                            info_raw: text.split("\\n").filter(t => t.trim().length > 0),
                            imagen: img,
                            enlace: link
                        };
                    }).filter(item => item.info_raw.length > 0);
                }""")

                if dom_items and len(dom_items) > 0:
                    nfts_capturados = dom_items

            if nfts_capturados:
                BASE_DE_DATOS_NFTS = nfts_capturados
                DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_capturados)} elementos capturados desde HofGamer."
            else:
                # Extraer título o estado HTML si todo falla para ver qué visualiza el navegador
                page_title = await page.title()
                DIAGNOSTICO_ESTADO = f"⚠️ Título de página: '{page_title}'. No se detectaron elementos de personajes en el DOM."

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
