from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from contextlib import asynccontextmanager

BASE_DE_DATOS_NFTS = []
DIAGNOSTICO_ESTADO = "Iniciando servidor..."

# --- Config de la llamada real a WEMIX PLAY ---
WEMIX_URL = "https://api.wemixplay.com/market/explore/v3/nfts"

WEMIX_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "es-ES,es;q=0.9",
    "content-type": "application/json",
    "origin": "https://wemixplay.com",
    "referer": "https://wemixplay.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
}

# Body base tomado de la petición real capturada en el navegador.
# page se sobreescribe al paginar.
WEMIX_BODY_BASE = {
    "sortOption": "byOldestOfferTime",
    "address": "0x1dbf9b33e59972ed753cae1423f4f23deec70cc9",
    "onAuction": True,
    "pagination": True,
    "pageSize": 20,
    "onLike": False,
    "addressFilter": [
        "0x0811a301173f15a8c4434138e78d41bbb5bf5e28",
        "0x1dbf9b33e59972ed753cae1423f4f23deec70cc9",
    ],
    "attrNumberOption": [],
    "attrStringOption": [],
    "onSale": True,
    "onBidding": True,
}


def parsear_nft(raw_item: dict) -> dict:
    """
    OJO: esto es un placeholder. En cuanto me pases un ejemplo real
    de la respuesta JSON, ajusto estas claves a las reales
    (name, level, price, tokenId, image, etc.) en vez de adivinar.
    """
    return {
        "id": raw_item.get("tokenId") or raw_item.get("id"),
        "name": raw_item.get("name") or raw_item.get("nftName") or "Desconocido",
        "class": raw_item.get("class") or raw_item.get("characterClass") or "N/A",
        "level": raw_item.get("level") or raw_item.get("lv") or "N/A",
        "power": raw_item.get("power") or raw_item.get("powerScore") or "N/A",
        "price": raw_item.get("price") or raw_item.get("salePrice") or "Consultar",
        "image": raw_item.get("image") or raw_item.get("imageUrl") or "",
        "url": f"https://wemixplay.com/@m4character_nft?tab=marketplace",
        "raw": raw_item,  # dejamos el objeto crudo mientras validamos el mapeo
    }


async def obtener_nfts_reales(paginas: int = 1):
    global BASE_DE_DATOS_NFTS, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "Consultando API oficial de WEMIX PLAY..."
    nfts_procesados = []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for page in range(1, paginas + 1):
                body = dict(WEMIX_BODY_BASE)
                body["page"] = page

                resp = await client.post(WEMIX_URL, headers=WEMIX_HEADERS, json=body)
                resp.raise_for_status()
                data = resp.json()

                # OJO: ajustar esta ruta según la forma real del JSON
                # (puede ser data["list"], data["data"]["items"], etc.)
                items = data.get("list") or data.get("items") or data.get("data") or []

                if not items:
                    break

                for raw in items:
                    nfts_procesados.append(parsear_nft(raw))

        if nfts_procesados:
            BASE_DE_DATOS_NFTS = nfts_procesados
            DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} NFTs reales cargados desde WEMIX PLAY."
        else:
            DIAGNOSTICO_ESTADO = "⚠️ La API respondió pero sin items. Revisar estructura del JSON."

    except httpx.HTTPStatusError as e:
        DIAGNOSTICO_ESTADO = f"❌ Error HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error: {str(e)}"


async def planificador_background():
    while True:
        await obtener_nfts_reales(paginas=1)
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
        "items": BASE_DE_DATOS_NFTS,
    }
