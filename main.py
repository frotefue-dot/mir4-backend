from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def parsear_detalles_tarjeta(lines, raw_href):
    CLASES_MIR4 = ["Arbalist", "Taoist", "Sorcerer", "Lancer", "Warrior", "Darkist", "Lionheart"]
    
    clase = "Desconocida"
    nombre = "Personaje MIR4"
    nivel = "N/A"
    poder = "N/A"
    precio_wemix = "0 WEMIX"
    precio_usd = ""

    # Limpiar y filtrar líneas basura comunes (como porcentajes de descuento, etc.)
    lines_filtradas = [l for l in lines if not l.startswith("-") and "%" not in l and "🔥" not in l and "🔨" not in l]

    for i, line in enumerate(lines_filtradas):
        line_clean = line.strip()
        
        # Detectar clase
        for c in CLASES_MIR4:
            if c.lower() in line_clean.lower():
                clase = c
                break

        # Detectar Nivel
        if "Lv." in line_clean:
            # Extraer formato Lv.XXX
            partes = line_clean.split("Lv.")
            if len(partes) > 1:
                nivel = "Lv." + partes[1].split()[0]

        # Detectar Poder (PS)
        if "PS" in line_clean or "ps" in line_clean:
            poder = line_clean

        # Detectar WEMIX o Precios numéricos
        if "WEMIX" in line_clean or "wemix" in line_clean:
            precio_wemix = line_clean
        elif line_clean.replace(',', '').isdigit() and i + 1 < len(lines_filtradas) and "WEMIX" in lines_filtradas[i+1]:
            precio_wemix = f"{line_clean} WEMIX"

        # Detectar USD
        if "$" in line_clean:
            precio_usd = line_clean

    # Buscar nombre si quedó genérico
    for line in lines_filtradas:
        if line not in CLASES_MIR4 and not "Lv." in line and not "PS" in line and not "WEMIX" in line and not "$" in line and len(line) > 2:
            nombre = line
            break

    # Si hay precio WEMIX pero no USD o viceversa
    precio_final = precio_wemix if precio_wemix != "0 WEMIX" else (precio_usd if precio_usd else "Consultar")

    if raw_href.startswith("http"):
        final_url = raw_href
    elif raw_href.startswith("/"):
        final_url = f"https://nft.hofgamer.com{raw_href}"
    else:
        final_url = f"https://nft.hofgamer.com/mir4/nft/{raw_href}"

    return {
        "name": nombre if nombre != "Personaje MIR4" else f"MIR4 {clase}",
        "class": clase,
        "level": nivel if nivel != "N/A" else "Lv. Desconocido",
        "power": poder if poder != "N/A" else "--- PS",
        "price": precio_final,
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

            await asyncio.sleep(4) # Tiempo para renderizado de JS de la página

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
                lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
                parsed = parsear_detalles_tarjeta(lines, item["href"])

                nfts_procesados.append({
                    "id": item["id"],
                    "name": parsed["name"],
                    "class": parsed["class"],
                    "level": parsed["level"],
                    "power": parsed["power"],
                    "price": parsed["price"],
                    "image": item["image"],
                    "url": parsed["url"]
                })

            BASE_DE_DATOS_NFTS = nfts_procesados
            DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} NFTs cargados."
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
    return {"status": "ok", "total": len(BASE_DE_DATOS_NFTS), "diagnostico": DIAGNOSTICO_ESTADO, "items": BASE_DE_DATOS_NFTS}
