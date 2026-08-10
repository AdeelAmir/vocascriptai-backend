import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

ALLOWED_COUNTRIES = [
    "PK",                                     # Pakistan
    "AE", "SA", "QA", "KW", "BH", "OM",      # Middle East
    "GB", "DE", "FR", "NL", "SE", "NO",       # Europe
    "DK", "CH", "AT", "BE",                   # Europe
    "US", "CA", "AU", "NZ",                   # North America & Oceania
]

EXCLUDED_PATHS = [
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
]


async def get_country_from_ip(ip: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"https://ipapi.co/{ip}/country/")
            if response.status_code == 200:
                return response.text.strip()
    except Exception:
        pass
    return None


class CountryRestrictionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        # Country restriction temporarily disabled
        return await call_next(request)

        # # Skip excluded paths
        # if request.url.path in EXCLUDED_PATHS:
        #     return await call_next(request)

        # # First check Vercel country header
        # country = request.headers.get("x-vercel-ip-country")

        # # If not available, detect from IP
        # if not country:
        #     ip = request.headers.get("x-forwarded-for")
        #     if ip:
        #         ip = ip.split(",")[0].strip()
        #     else:
        #         ip = request.client.host if request.client else None

        #     # Skip check for localhost
        #     if ip and ip in ("127.0.0.1", "::1", "localhost"):
        #         return await call_next(request)

        #     if ip:
        #         country = await get_country_from_ip(ip)

        # # If country detected and not allowed → block
        # if country and country not in ALLOWED_COUNTRIES:
        #     return JSONResponse(
        #         status_code=403,
        #         content={"error": "Service not available in your region."}
        #     )