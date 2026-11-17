"""Backup consistente e verificação de integridade do SQLite do AgendaSimples.

Uso:
    python backup_sqlite.py backup --destino /caminho/externo/backup.db
    python backup_sqlite.py verificar --arquivo /caminho/externo/backup.db

Não restaura automaticamente nem envia dados para serviços externos.
"""
import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from database import DATABASE


def verificar(arquivo):
    caminho = Path(arquivo).expanduser().resolve()
    if not caminho.is_file():
        raise ValueError("Arquivo de backup não encontrado.")
    # Modo somente leitura: jamais cria ou modifica o arquivo inspecionado.
    with sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True, timeout=15) as conexao:
        resultado = conexao.execute("PRAGMA integrity_check").fetchone()
        if not resultado or resultado[0] != "ok":
            raise ValueError("Falha na verificação de integridade do SQLite.")
        tabelas = {
            linha[0] for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        obrigatorias = {"profissional", "servico", "cliente", "agendamento"}
        if not obrigatorias.issubset(tabelas):
            raise ValueError("O arquivo não contém as tabelas essenciais do AgendaSimples.")
    return caminho


def backup(destino):
    origem = DATABASE.expanduser().resolve()
    saida = Path(destino).expanduser().resolve()
    if not origem.is_file():
        raise ValueError("Banco de origem não encontrado; backup não realizado.")
    if saida == origem:
        raise ValueError("O destino não pode ser o banco em uso.")
    if saida.exists():
        raise ValueError("O destino já existe. Escolha um nome novo para preservar backups anteriores.")
    if not saida.parent.is_dir():
        raise ValueError("A pasta de destino precisa existir.")
    # Arquivo temporário no mesmo diretório para publicação atômica.
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".agendasimples-backup-", suffix=".db",
            dir=saida.parent, delete=False
        ) as arquivo:
            temporario = Path(arquivo.name)
        with sqlite3.connect(
            origem.as_uri() + "?mode=ro", uri=True, timeout=15
        ) as fonte, sqlite3.connect(temporario, timeout=15) as copia:
            fonte.execute("PRAGMA busy_timeout = 15000")
            fonte.backup(copia, pages=100, sleep=0.1)
        verificar(temporario)
        # Evita substituir um backup existente em caso de concorrência.
        if saida.exists():
            raise ValueError("Destino criado durante o backup; operação cancelada.")
        os.link(temporario, saida)
        return saida
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Backup seguro do AgendaSimples")
    sub = parser.add_subparsers(dest="acao", required=True)
    criar = sub.add_parser("backup", help="Criar cópia consistente do banco")
    criar.add_argument("--destino", required=True)
    checar = sub.add_parser("verificar", help="Verificar um backup existente")
    checar.add_argument("--arquivo", required=True)
    args = parser.parse_args()
    try:
        if args.acao == "backup":
            arquivo = backup(args.destino)
            print(f"Backup criado e verificado: {arquivo}")
        else:
            arquivo = verificar(args.arquivo)
            print(f"Integridade confirmada: {arquivo}")
    except (OSError, sqlite3.Error, ValueError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
