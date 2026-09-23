from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import re
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def parsear_detalles_tarjeta(lines, raw_href):
    # Clases conocidas de MIR4
    CLASES_MIR4 = ["Arbalist", "Taoist", "Sorcerer", "Lancer", "Warrior", "Darkist", "Lionheart"]
    
    clase = "Desconocida"
    nombre = "Personaje MIR4"
    nivel = "N/A"
    poder = "N/A"
    precio_wemix = "Consultar"
    precio_usd = ""

    # 1. Identificar Clase, Nombre y Nivel desde las líneas de texto
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Detectar clase
        if line_clean in CLASES_MIR4:
            clase = line_clean
            # Normalmente el nombre del personaje viene justo después de la clase
            if i + 1 < len(lines) and not lines[i+1].startswith("Lv."):
                nombre = lines[i+1].strip()

        # Detectar Nivel
        if line_clean.startswith("Lv."):
            nivel = line_clean

        # Detectar Poder (PS)
        if "PS" in line_clean:
            poder = line_clean

        # Detectar WEMIX
        if "WEMIX" in line_clean:
            precio_wemix = line_clean
        elif line_clean.isdigit() and i + 1 < len(lines) and lines[i+1] == "WEMIX":
            precio_wemix = f"{line_clean} WEMIX"

        # Detectar USD
        if "≈ $" in line_clean or line_clean.startswith("$"):
            precio_usd = line_clean

    # Si no se encontró nombre específico, usar el nombre por defecto
    if nombre == "Personaje MIR4" and len(lines) > 0:
        for line in lines:
            if line not in CLASES_MIR4 and not line.startswith("Lv.") and "PS" not in line and "WEMIX" not in line and "🔥" not in line and "🔨" not in line:
                nombre = line
                break

    # Construir precio final
    precio_final = f"{precio_wemix} ({precio_usd})" if precio_usd else precio_wemix

    # Normalización estricta de la URL
    if raw_href.startswith("http"):
        final_url = raw_href
    elif raw_href.startswith("/"):
        final_url = f"https://nft.hofgamer.com{raw_href}"
    else:
        final_url = f"https://nft.hofgamer.com/mir4/nft/{raw_href}"

    return {
        "name": nombre,
        "character_name": nombre,
        "class": clase,
        "level": nivel,
        "power": poder,
        "price": precio_final,
        "url": final_url,
        "link": final_url
    }

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "🔄 Abriendo Chromium en Render..."
    nfts_procesados = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )

            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1400, "height": 900}
            )

            page = await context.new_page()
            url_target = "https://nft.hofgamer.com/mir4/?limit=48&page=1"
            DIAGNOSTICO_ESTADO = f"🌐 Cargando {url_target}..."
            await page.goto(url_target, wait_until="domcontentloaded", timeout=60000)

            try:
                await page.wait_for_selector("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']", timeout=15000)
            except Exception:
                await asyncio.sleep(5)

            DIAGNOSTICO_ESTADO = "🔍 Extrayendo y parseando datos..."
            
            raw_cards = await page.evaluate("""() => {
                const cards = Array.from(document.querySelectorAll("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']"));
                return cards.map((c, idx) => {
                    const text = c.innerText || "";
                    const img = c.querySelector("img") ? c.querySelector("img").src : "";
                    
                    let href = c.getAttribute("href") || "";
                    if (!href && c.querySelector("a")) {
                        href = c.querySelector("a").getAttribute("href") || "";
                    }

                    return {
                        id: idx + 1,
                        text: text,
                        image: img,
                        href: href
                    };
                }).filter(item => item.text.trim().length > 0);
            }""")

            for item in raw_cards:
                lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
                parsed = parsear_detalles_tarjeta(lines, item["href"])

                nfts_procesados.append({
                    "id": item["id"],
                    "name": parsed["name"],
                    "character_name": parsed["character_name"],
                    "class": parsed["class"],
                    "level": parsed["level"],
                    "power": parsed["power"],
                    "price": parsed["price"],
                    "image": item["image"],
                    "icon": item["image"],
                    "url": parsed["url"],
                    "link": parsed["link"]
                })

            if nfts_procesados:
                BASE_DE_DATOS_NFTS = nfts_procesados
                DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} personajes cargados."
            else:
                DIAGNOSTICO_ESTADO = "⚠️ No se detectaron tarjetas en la página."

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
