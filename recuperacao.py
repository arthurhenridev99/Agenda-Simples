"""Links temporários de recuperação e envio por SMTP com TLS."""
import hashlib
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit

from flask import current_app
from itsdangerous import URLSafeTimedSerializer


def email_valido(email):
    return len(email) <= 254 and re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", email) is not None


def assinatura_senha(senha_hash):
    return hashlib.sha256(senha_hash.encode()).hexdigest()


def serializador():
    return URLSafeTimedSerializer(current_app.secret_key, salt="agendasimples-recuperacao-v1")


def gerar_token(profissional):
    return serializador().dumps({"id": profissional[0], "senha": assinatura_senha(profissional[1])})


def configuracao_email():
    nomes = ('SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'SMTP_FROM', 'APP_BASE_URL')
    config = {nome: os.environ.get(nome, '').strip() for nome in nomes}
    config['SMTP_PASSWORD'] = os.environ.get('SMTP_PASSWORD', '')
    if not all(config.values()) or not os.environ.get('FLASK_SECRET_KEY'):
        return None
    url = urlsplit(config['APP_BASE_URL'])
    if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query or url.fragment:
        return None
    if url.scheme != 'https' and url.hostname not in ('localhost', '127.0.0.1'):
        return None
    if not email_valido(config['SMTP_FROM']):
        return None
    try:
        config['SMTP_PORT'] = int(config['SMTP_PORT'])
        if not 1 <= config['SMTP_PORT'] <= 65535:
            return None
    except ValueError:
        return None
    return config


def enviar_recuperacao(email, caminho, config):
    mensagem = EmailMessage()
    mensagem['Subject'] = 'Redefina sua senha — AgendaSimples'
    mensagem['From'] = config['SMTP_FROM']
    mensagem['To'] = email
    link = config['APP_BASE_URL'].rstrip('/') + caminho
    mensagem.set_content(
        'Recebemos uma solicitação para redefinir sua senha no AgendaSimples.\n\n'
        f'Acesse este link em até 30 minutos:\n{link}\n\n'
        'Se não foi você, ignore este e-mail. Sua senha continua a mesma.\n'
    )
    contexto = ssl.create_default_context()
    if config['SMTP_PORT'] == 465:
        with smtplib.SMTP_SSL(config['SMTP_HOST'], 465, timeout=15, context=contexto) as smtp:
            smtp.login(config['SMTP_USER'], config['SMTP_PASSWORD'])
            smtp.send_message(mensagem)
    else:
        with smtplib.SMTP(config['SMTP_HOST'], config['SMTP_PORT'], timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=contexto)
            smtp.ehlo()
            smtp.login(config['SMTP_USER'], config['SMTP_PASSWORD'])
            smtp.send_message(mensagem)
