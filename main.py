from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

BASE_DE_DATOS_NFTS: List[Dict[str, Any]] = []
NFTS_POR_ID: Dict[int, Dict[str, Any]] = {}
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


def parsear_nft(raw_item: dict) -> dict | None:
    """
    Mapeo basado en el esquema REAL de /market/explore/v3/nfts.
    - Los atributos del personaje vienen en metaData.attributes como
      pares {key, value}: PowerScore, Level, Class, Server, CharacterName, NFTEnhancement.
    - El precio de la orden activa viene en wei (18 decimales) en order.price.amount,
      y ya trae su equivalente en USD en order.price.dollarPrice.
    - metaData.external_url ya es el link OFICIAL y verificable a xdraco.com,
      no hay que construirlo ni adivinarlo.
    """
    meta = raw_item.get("metaData") or {}
    order = raw_item.get("order") or {}
    price_obj = order.get("price") or {}

    attrs = {a.get("key"): a.get("value") for a in meta.get("attributes", []) if a.get("key")}

    if not attrs and not meta:
        return None

    precio_wemix = None
    amount_raw = price_obj.get("amount")
    if amount_raw not in (None, ""):
        try:
            precio_wemix = round(int(amount_raw) / 1e18, 2)
        except (ValueError, TypeError):
            precio_wemix = None

    precio_usd = price_obj.get("dollarPrice")
    try:
        precio_usd = round(float(precio_usd), 2) if precio_usd is not None else None
    except (ValueError, TypeError):
        precio_usd = None

    status = raw_item.get("currentStatus") or {}

    tid = raw_item.get("tid") or order.get("tid")
    try:
        tid_int = int(tid) if tid is not None else None
    except (ValueError, TypeError):
        tid_int = None

    return {
        "id": tid_int,
        "name": attrs.get("CharacterName") or raw_item.get("nftName") or "Desconocido",
        "class": attrs.get("Class") or "N/A",
        "level": attrs.get("Level"),
        "power": attrs.get("PowerScore"),
        "enhancement": attrs.get("NFTEnhancement", 0),
        "server": attrs.get("Server"),
        "price_wemix": precio_wemix,
        "price_usd": precio_usd,
        "price_display": (
            f"{precio_wemix:,} WEMIX (≈${precio_usd:,})"
            if precio_wemix is not None and precio_usd is not None
            else "Consultar"
        ),
        "image": meta.get("image") or raw_item.get("nftImage") or "",
        "url": meta.get("external_url") or "",
        "is_auction": status.get("isAuction", False),
        "is_bidding": status.get("isBidding", False),
        "sale_deadline_unix": order.get("saleDeadLineTime"),
        "raw": raw_item,
    }


async def obtener_nfts_reales(max_paginas: int = 30):
    """
    Pagina automáticamente usando el totalCount que la propia API reporta,
    hasta cubrir todo el mercado o hasta max_paginas (límite de seguridad
    para no martillar la API de WEMIX PLAY con demasiadas peticiones seguidas).
    """
    global BASE_DE_DATOS_NFTS, NFTS_POR_ID, DIAGNOSTICO_ESTADO
    DIAGNOSTICO_ESTADO = "Consultando API oficial de WEMIX PLAY..."
    nfts_procesados: List[Dict[str, Any]] = []
    total_reportado = None

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            page = 1
            while True:
                body = dict(WEMIX_BODY_BASE)
                body["page"] = page

                resp = await client.post(WEMIX_URL, headers=WEMIX_HEADERS, json=body)
                resp.raise_for_status()
                data = resp.json()

                if data.get("result") != 0:
                    DIAGNOSTICO_ESTADO = f"⚠️ API respondió error: {data.get('resultString')} - {data.get('desc')}"
                    break

                payload = data.get("data") or {}
                total_reportado = payload.get("totalCount", total_reportado)
                items = payload.get("result") or []

                if not items:
                    break

                for raw in items:
                    parsed = parsear_nft(raw)
                    if parsed is not None:
                        nfts_procesados.append(parsed)

                if total_reportado is not None and len(nfts_procesados) >= total_reportado:
                    break

                page += 1
                if page > max_paginas:
                    break

                await asyncio.sleep(0.5)

        if nfts_procesados:
            BASE_DE_DATOS_NFTS = nfts_procesados
            NFTS_POR_ID = {
                nft["id"]: nft
                for nft in nfts_procesados
                if nft.get("id") is not None
            }
            extra = f" de {total_reportado} reportados por la API" if total_reportado else ""
            DIAGNOSTICO_ESTADO = f"✅ Éxito: {len(nfts_procesados)} NFTs reales cargados desde WEMIX PLAY{extra}."
        else:
            DIAGNOSTICO_ESTADO = "⚠️ La API respondió pero sin items. Revisar estructura del JSON."

    except httpx.HTTPStatusError as e:
        DIAGNOSTICO_ESTADO = f"❌ Error HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        DIAGNOSTICO_ESTADO = f"❌ Error: {str(e)}"


def separar_inventario(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Separación genérica del inventario en tradeables y bound.
    Esta función queda lista para usar con la respuesta real del API de XDRACO/WEMIX.
    """
    tradeables = []
    bound = []

    for item in items:
        is_tradeable = bool(item.get("tradeable"))
        is_bound = bool(item.get("bound"))

        if is_tradeable and not is_bound:
            tradeables.append(item)
        else:
            bound.append(item)

    return {
        "tradeables": tradeables,
        "bound": bound,
    }


async def obtener_inventario_xdraco(nft_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Función preparada para integrar el API oficial de XDRACO/WEMIX.
    Sustituye la URL y el parseo interno por el endpoint real cuando lo tengas.
    """
    # ---------------------------------------------------------------------
    # AQUÍ DEBES PONER EL ENDPOINT REAL DEL INVENTARIO
    # Ejemplo de estructura:
    #
    # XDRACO_INVENTORY_URL = f"https://api....../{nft_id}/inventory"
    #
    # async with httpx.AsyncClient(timeout=20) as client:
    #     resp = await client.get(XDRACO_INVENTORY_URL, headers=WEMIX_HEADERS)
    #     resp.raise_for_status()
    #     data = resp.json()
    #
    #     items_raw = data.get("items") or data.get("result") or []
    #     normalized = [normalizar_item_inventario(x) for x in items_raw]
    #     return separar_inventario(normalized)
    # ---------------------------------------------------------------------

    # Placeholder seguro mientras conectas el endpoint real:
    # si todavía no está conectado, devuelve inventario vacío.
    return {
        "tradeables": [],
        "bound": [],
    }


def obtener_nft_por_id(nft_id: int) -> Optional[Dict[str, Any]]:
    return NFTS_POR_ID.get(nft_id)


async def construir_detalle_nft(nft_id: int) -> Optional[Dict[str, Any]]:
    nft = obtener_nft_por_id(nft_id)

    if not nft:
        return None

    inventario = await obtener_inventario_xdraco(nft_id)

    return {
        "status": "ok",
        "nft": {
            "id": nft.get("id"),
            "name": nft.get("name"),
            "class": nft.get("class"),
            "level": nft.get("level"),
            "power": nft.get("power"),
            "enhancement": nft.get("enhancement"),
            "server": nft.get("server"),
            "price_wemix": nft.get("price_wemix"),
            "price_usd": nft.get("price_usd"),
            "price_display": nft.get("price_display"),
            "image": nft.get("image"),
            "url": nft.get("url"),
            "is_auction": nft.get("is_auction"),
            "is_bidding": nft.get("is_bidding"),
            "sale_deadline_unix": nft.get("sale_deadline_unix"),
        },
        "inventory": inventario,
    }


async def planificador_background():
    while True:
        await obtener_nfts_reales()
        await asyncio.sleep(900)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(planificador_background())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "diagnostico": DIAGNOSTICO_ESTADO,
        "total_nfts": len(BASE_DE_DATOS_NFTS),
    }


@app.get("/api/nfts")
async def obtener_nfts():
    return {
        "status": "ok",
        "total": len(BASE_DE_DATOS_NFTS),
        "diagnostico": DIAGNOSTICO_ESTADO,
        "items": BASE_DE_DATOS_NFTS,
    }


@app.get("/api/nft/{nft_id}")
async def obtener_nft_detalle(nft_id: int):
    detalle = await construir_detalle_nft(nft_id)

    if not detalle:
        raise HTTPException(status_code=404, detail="NFT no encontrado")

    return detalle


@app.get("/api/nft/{nft_id}/inventory")
async def obtener_inventario_nft(nft_id: int):
    nft = obtener_nft_por_id(nft_id)
    if not nft:
        raise HTTPException(status_code=404, detail="NFT no encontrado")

    inventario = await obtener_inventario_xdraco(nft_id)
    return {
        "status": "ok",
        "nft_id": nft_id,
        "inventory": inventario,
    }
