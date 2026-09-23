from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import re
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "🔄 Abriendo Chromium en Render..."
    nfts_procesados = []

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

            url_target = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            DIAGNOSTICO_ESTADO = f"🌐 Cargando {url_target}..."
            await page.goto(url_target, wait_until="domcontentloaded", timeout=60000)

            DIAGNOSTICO_ESTADO = "⏳ Esperando renderizado de tarjetas en pantalla..."
            
            try:
                await page.wait_for_selector("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']", timeout=15000)
            except Exception:
                await asyncio.sleep(5)

            DIAGNOSTICO_ESTADO = "🔍 Extrayendo y formateando personajes..."
            
            # Scraping directo en el DOM
            raw_cards = await page.evaluate("""() => {
                const cards = Array.from(document.querySelectorAll("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']"));
                return cards.map((c, idx) => {
                    const text = c.innerText || "";
                    const img = c.querySelector("img") ? c.querySelector("img").src : "";
                    const link = c.tagName === "A" ? c.href : (c.querySelector("a") ? c.querySelector("a").href : "");
                    return {
                        id: idx + 1,
                        text: text,
                        image: img,
                        link: link
                    };
                }).filter(item => item.text.trim().length > 0);
            }""")

            # Procesar y limpiar la información para el Frontend
            for item in raw_cards:
                lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
                
                # Extracción de precio, poder y nivel con expresiones regulares
                full_text = " ".join(lines)
                
                # Buscar patrón de precio (ej. 150 DRACO, $50, etc)
                price_match = re.search(r'(\d+[\d,.]*\s*(USD|DRACO|HYDRA|WEMIX|\$))', full_text, re.IGNORECASE)
                price = price_match.group(1) if price_match else (lines[-1] if len(lines) > 2 else "Consultar")

                # Buscar poder (PS / Power)
                power_match = re.search(r'(\d{3,6}[\d,.]*)', full_text)
                power = power_match.group(1) if power_match else "N/A"

                nombre = lines[0] if len(lines) > 0 else f"Personaje #{item['id']}"

                nfts_procesados.append({
                    "id": item["id"],
                    "name": nombre,
                    "title": nombre,
                    "power": power,
                    "price": price,
                    "image": item["image"],
                    "url": item["link"],
                    "details": lines
                })

            if nfts_procesados:
                BASE_DE_DATOS_NFTS = nfts_procesados
                DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} personajes cargados."
            else:
                DIAGNOSTICO_ESTADO = "⚠️ No se detectaron tarjetas visuales en la página."

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
