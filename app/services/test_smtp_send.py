# test_smtp_send.py
from app.email_sender.SMTP import send_verification_email

result = send_verification_email("adnansaeed.datascientist@gmail.com", "123456")
print("Result:", result)