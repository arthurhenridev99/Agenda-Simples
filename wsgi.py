"""Entrada WSGI para hospedagem do AgendaSimples.

Configure DATABASE_PATH para um volume persistente antes de iniciar o servidor.
Exemplo (Linux): gunicorn --workers 1 wsgi:app
"""
from database import inicializar_banco

# Prepara as tabelas e migrações aditivas antes de receber requisições.
inicializar_banco()

from app import app  # noqa: E402
