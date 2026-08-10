import asyncio

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

# from app.email_sender.email_send import send_contact_email
from app.email_sender.SMTP import send_contact_email

router = APIRouter()


class ContactForm(BaseModel):
    name: str
    email: EmailStr
    message: str = Field(min_length=1)


@router.post("/contact")
async def submit_contact_form(body: ContactForm) -> dict[str, object]:
    success = await asyncio.to_thread(send_contact_email, body.name, body.email, body.message)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send your message. Please try again later.",
        )

    return {"success": True, "message": "Your message has been sent successfully."}