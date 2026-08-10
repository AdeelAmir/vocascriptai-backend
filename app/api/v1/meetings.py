import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.models.user import User
from app.services.pricing_entitlements import PricingEntitlementService
from app.services.pdf import generate_report_pdf

router = APIRouter()

class TranscriptSegment(BaseModel):
    speaker: str
    timestamp: str
    text: str

class ActionItem(BaseModel):
    type: str
    title: str
    description: str
    prompt: str

class MeetingPdfRequest(BaseModel):
    meeting_id: str
    title: str
    created_at: str
    file_duration: str
    summary: str
    action_items: list[ActionItem]
    transcript: list[TranscriptSegment]

@router.post("/generate-pdf")
async def generate_pdf(
    data: MeetingPdfRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication is required to download a PDF.")
        payload = verify_token(auth_header.split(" ", 1)[1])
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        if payload.get("type") == "admin" and payload.get("role") == 1:
            pass
        elif payload.get("type") == "user" and payload.get("role") == 2:
            user_id = uuid.UUID(str(payload.get("sub")))
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="User account is unavailable.")
            entitlement = await PricingEntitlementService.get_current_entitlement(user, db)
            if not entitlement.capabilities.get("pdf_download_enabled", False):
                raise HTTPException(status_code=403, detail="PDF download is not included in your current plan.")
        else:
            raise HTTPException(status_code=403, detail="Access denied.")
        pdf_bytes = generate_report_pdf(data.model_dump())
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=briefroom_report_{data.meeting_id}.pdf"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
