import smtplib

def test_smtp():
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.ehlo()
        server.starttls()
        print("SUCCESS: SMTP port 587 is open and working")
        server.quit()
    except Exception as e:
        print(f"FAILED: {e}")

test_smtp()