"""Limpeza administrativa controlada do banco SQLite do AgendaSimples.

NÃO é executado pelo deploy nem pela aplicação web.
Uso:
    python limpar_banco.py
    python limpar_banco.py --executar --confirmar LIMPAR-AGENDASIMPLES

Antes de executar: parar o serviço e preservar uma cópia externa do banco.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

TABELAS = (
    "notificacao",
    "agendamento",
    "bloqueio",
    "horario_atendimento",
    "servico",
    "cliente",
    "profissional",
)
OPCIONAIS = ("limite_login",)
CONFIRMACAO = "LIMPAR-AGENDASIMPLES"


def main():
    parser = argparse.ArgumentParser(description="Limpeza controlada dos dados do AgendaSimples")
    parser.add_argument("--executar", action="store_true", help="Autoriza execução destrutiva")
    parser.add_argument("--confirmar", default="", help="Frase de confirmação obrigatória")
    args = parser.parse_args()

    # Exige a variável explícita para evitar limpar um banco local por engano.
    caminho_env = os.environ.get("DATABASE_PATH")
    if not caminho_env:
        parser.error("DATABASE_PATH não está configurado. Nenhuma alteração realizada.")
    caminho = Path(caminho_env).expanduser().resolve()
    if not caminho.is_file():
        parser.error("Banco não encontrado. Nenhuma alteração realizada.")

    conexao = sqlite3.connect(caminho, timeout=15)
    try:
        conexao.execute("PRAGMA busy_timeout = 15000")
        conexao.execute("PRAGMA foreign_keys = ON")
        existentes = {
            linha[0]
            for linha in conexao.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        ausentes = set(TABELAS) - existentes
        desconhecidas = existentes - set(TABELAS) - set(OPCIONAIS)
        if ausentes or desconhecidas:
            raise ValueError(
                f"Estrutura inesperada: tabelas ausentes={sorted(ausentes)}, "
                f"tabelas não reconhecidas={sorted(desconhecidas)}. Nada foi excluído."
            )

        apagar = [t for t in TABELAS + OPCIONAIS if t in existentes]
        contagens = {t: conexao.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in apagar}
        print(f"Banco: {caminho}")
        for tabela, quantidade in contagens.items():
            print(f"  {tabela}: {quantidade} registro(s)")

        if not args.executar:
            print("\nSIMULAÇÃO: nenhuma alteração realizada.")
            print("Antes da execução, pare o serviço e preserve uma cópia externa do banco.")
            return 0

        if args.confirmar != CONFIRMACAO:
            raise ValueError("Confirmação inválida. Nenhuma alteração realizada.")
        # Proteção adicional contra execução em banco inesperado.
        if caminho != Path("/data/agendamento.db"):
            raise ValueError("Caminho diferente do banco de produção confirmado. Nenhuma alteração realizada.")

        conexao.execute("BEGIN IMMEDIATE")
        try:
            for tabela in apagar:
                conexao.execute(f'DELETE FROM "{tabela}"')
            # Mantém a estrutura e reinicia contadores de IDs quando presentes.
            if conexao.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            ).fetchone():
                for tabela in apagar:
                    conexao.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tabela,))
            erros = conexao.execute("PRAGMA foreign_key_check").fetchall()
            if erros:
                raise ValueError("Falha na integridade referencial; transação cancelada.")
            conexao.commit()
        except Exception:
            conexao.rollback()
            raise

        print("Limpeza concluída: registros removidos, tabelas preservadas.")
        return 0
    except (sqlite3.Error, ValueError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    finally:
        conexao.close()


if __name__ == "__main__":
    raise SystemExit(main())
