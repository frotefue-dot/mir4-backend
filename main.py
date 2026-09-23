from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
from contextlib import asynccontextmanager
import re

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def parsear_detalles_tarjeta(text_block, raw_href, img_url):
    CLASES_MIR4 = ["Arbalist", "Taoist", "Sorcerer", "Lancer", "Warrior", "Darkist", "Lionheart"]
    
    clase = "Warrior"
    nombre = "Personaje MIR4"
    nivel = "Lv. 100"
    poder = "300,000 PS"
    precio = "1,000 WEMIX"

    # Limpiar líneas vacías y duplicadas
    lines = [l.strip() for l in text_block.split("\n") if l.strip()]

    # 1. Detectar Clase
    for line in lines:
        for c in CLASES_MIR4:
            if c.lower() in line.lower():
                clase = c
                break

    # 2. Detectar Nivel
    for line in lines:
        if "lv" in line.lower() or "level" in line.lower():
            nums = re.findall(r'\d+', line)
            if nums:
                nivel = f"Lv. {nums[0]}"
                break

    # 3. Detectar Poder (PS)
    for line in lines:
        if "ps" in line.lower() or ("," in line and line.replace(",", "").isdigit() and len(line.replace(",", "")) >= 5):
            nums = re.findall(r'[\d,]+', line)
            if nums:
                poder = f"{nums[0]} PS"
                break

    # 4. Detectar Precio
    for line in lines:
        if "wemix" in line.lower() or "$" in line:
            precio = line
            break

    # 5. Detectar Nombre Real (excluyendo metadatos)
    for line in lines:
        line_lower = line.lower()
        is_clase = any(c.lower() in line_lower for c in CLASES_MIR4)
        is_lvl = "lv" in line_lower or "level" in line_lower
        is_ps = "ps" in line_lower
        is_price = "wemix" in line_lower or "$" in line or line.replace(",", "").isdigit()
        
        if not is_clase and not is_lvl and not is_ps and not is_price and len(line) > 2:
            nombre = line
            break

    # Construir URL final
    if raw_href.startswith("http"):
        final_url = raw_href
    elif raw_href.startswith("/"):
        final_url = f"https://nft.hofgamer.com{raw_href}"
    else:
        final_url = f"https://nft.hofgamer.com/mir4/nft/{raw_href}"

    return {
        "name": nombre,
        "class": clase,
        "level": nivel,
        "power": poder,
        "price": precio,
        "image": img_url if img_url else "https://www.xdraco.com/nft/assets/img/common/thumb-default.png",
        "url": final_url
    }

async def obtener_nfts_con_playwright():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "🔄 Sincronizando con HofGamer..."
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
            await page.goto("https://nft.hofgamer.com/mir4/?limit=48&page=1", wait_until="domcontentloaded", timeout=60000)

            await asyncio.sleep(5)

            raw_cards = await page.evaluate("""() => {
                const cards = Array.from(document.querySelectorAll("a[href*='/character/'], a[href*='/nft/'], div[class*='card'], div[class*='item']"));
                return cards.map((c, idx) => {
                    const text = c.innerText || "";
                    const img = c.querySelector("img") ? c.querySelector("img").src : "";
                    let href = c.getAttribute("href") || (c.querySelector("a") ? c.querySelector("a").getAttribute("href") : "");
                    return { id: idx + 1, text, image: img, href };
                }).filter(item => item.text.trim().length > 0);
            }""")

            for item in raw_cards:
                parsed = parsear_detalles_tarjeta(item["text"], item["href"], item["image"])

                nfts_procesados.append({
                    "id": item["id"],
                    "name": parsed["name"],
                    "class": parsed["class"],
                    "level": parsed["level"],
                    "power": parsed["power"],
                    "price": parsed["price"],
                    "image": parsed["image"],
                    "url": parsed["url"]
                })

            BASE_DE_DATOS_NFTS = nfts_procesados
            DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} NFTs sincronizados."
            await browser.close()
    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error: {str(e)}"

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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/nfts")
async def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
