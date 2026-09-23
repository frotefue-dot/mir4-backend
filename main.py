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

            DIAGNOSTICO_ESTADO = "🔍 Extrayendo tarjetas del DOM..."
            
            # Extraer elementos desde el DOM de la página
            raw_cards = await page.evaluate("""() => {
                const cards = Array.from(document.querySelectorAll("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']"));
                return cards.map((c, idx) => {
                    const text = c.innerText || "";
                    const img = c.querySelector("img") ? c.querySelector("img").src : "";
                    
                    // Obtener el atributo href directo del elemento o de sus hijos
                    let href = c.getAttribute("href") || "";
                    if (!href && c.querySelector("a")) {
                        href = c.querySelector("a").getAttribute("href") || "";
                    }
                    if (!href && c.tagName === "A") {
                        href = c.href;
                    }

                    return {
                        id: idx + 1,
                        text: text,
                        image: img,
                        href: href
                    };
                }).filter(item => item.text.trim().length > 0);
            }""")

            # Procesar y estandarizar las tarjetas
            for item in raw_cards:
                lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
                full_text = " ".join(lines)
                
                # Extracción de Precio
                price_match = re.search(r'(\d+[\d,.]*\s*(USD|DRACO|HYDRA|WEMIX|\$))', full_text, re.IGNORECASE)
                price = price_match.group(1) if price_match else (lines[-1] if len(lines) > 2 else "Consultar")

                # Extracción de Poder (PS)
                power_match = re.search(r'(\d{3,6}[\d,.]*)', full_text)
                power = power_match.group(1) if power_match else "N/A"

                nombre = lines[0] if len(lines) > 0 else f"Personaje #{item['id']}"

                # Normalización del enlace para dirigir correctamente a MIR4 / HofGamer NFT
                raw_href = item.get("href", "")
                if raw_href.startswith("http"):
                    final_url = raw_href
                elif raw_href.startswith("/"):
                    final_url = f"https://nft.hofgamer.com{raw_href}"
                elif raw_href:
                    final_url = f"https://nft.hofgamer.com/mir4/{raw_href}"
                else:
                    final_url = "https://nft.hofgamer.com/mir4/"

                # Objeto con claves compatibles para cualquier tipo de frontend
                nfts_procesados.append({
                    "id": item["id"],
                    "name": nombre,
                    "character_name": nombre,
                    "title": nombre,
                    "power": power,
                    "price": price,
                    "image": item["image"],
                    "icon": item["image"],
                    "url": final_url,
                    "link": final_url,
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
