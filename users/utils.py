import random
import string
from django.core.mail import send_mail
from django.conf import settings

def generate_password(length=12):
    """
    Generate a random password consisting of letters and digits.

    Args:
        length (int): Length of the password. Default is 12.

    Returns:
        str: The generated password.
    """
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def send_user_email(to_email, subject, plain_text_content, html_content=None):
    """
    Send an email to a user.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject.
        plain_text_content (str): Plain text version of the email content.
        html_content (str or None): Optional HTML content for the email.

    Raises:
        Exception: Raises exception if sending email fails.
    """
    send_mail(
        subject,
        plain_text_content,
        settings.EMAIL_HOST_USER,
        [to_email],
        fail_silently=False,
        html_message=html_content
    )
