from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import threading
import time
import urllib.parse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ⚠️ PEGA AQUÍ TU API KEY REAL DE SCRAPERAPI (entre las comillas)
SCRAPER_API_KEY = "dcc45acdd5909e73b6be2daf0c2edeb7"

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

def actualizar_subastas_xdraco():
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    print("🔄 Consultando xDRACO con renderizado JavaScript...")
    nfts_acumulados = []

    for page in range(1, 4):
        # Subdominio corregido a nft.xdraco.com
        url_target = f"https://nft.xdraco.com/api/nft/lists?listType=sale&languageCode=es&page={page}"
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={urllib.parse.quote(url_target)}&render=true"
        
        try:
            res = requests.get(proxy_url, timeout=35)
            contenido = res.text.strip()
            
            if res.status_code == 200 and contenido.startswith("{"):
                data = res.json()
                items = data.get("data", {}).get("lists", [])
                nfts_acumulados.extend(items)
            else:
                preview = contenido[:70].replace("\n", " ")
                if contenido.startswith("<"):
                    DIAGNOSTICO_ESTADO = f"Página {page}: Recibido HTML en lugar de JSON. Vista previa: {preview}"
                else:
                    DIAGNOSTICO_ESTADO = f"Página {page}: HTTP {res.status_code} - Detalle: {preview}"
                break
        except Exception as e:
            DIAGNOSTICO_ESTADO = f"Error de conexión en página {page}: {str(e)}"
            break

    if nfts_acumulados:
        BASE_DE_DATOS_NFTS = nfts_acumulados
        DIAGNOSTICO_ESTADO = f"✅ Éxito total: {len(nfts_acumulados)} personajes cargados desde xDRACO."

def planificador_background():
    actualizar_subastas_xdraco()
    while True:
        time.sleep(900)
        actualizar_subastas_xdraco()

threading.Thread(target=planificador_background, daemon=True).start()

@app.get("/api/nfts")
def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS
    }
