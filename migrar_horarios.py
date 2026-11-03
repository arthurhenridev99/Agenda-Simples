import sqlite3
from pathlib import Path

PASTA = Path(__file__).resolve().parent
BANCO = PASTA / "agendamento.db"
BACKUP = PASTA / "agendamento_backup_pre_uc12.db"


def migrar():
    if not BANCO.is_file() or not BACKUP.is_file():
        raise RuntimeError("Banco ou backup não encontrado.")

    conexao = sqlite3.connect(BANCO)
    conexao.execute("PRAGMA foreign_keys = ON")

    try:
        quantidade = conexao.execute(
            "SELECT COUNT(*) FROM horario_atendimento"
        ).fetchone()[0]

        if quantidade != 0:
            raise RuntimeError("A tabela possui horários. Migração cancelada.")

        # Impedir a migração se outra tabela depender
        # diretamente de horario_atendimento.
        tabelas = conexao.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

        for (tabela,) in tabelas:
            referencias = conexao.execute(
                f'PRAGMA foreign_key_list("{tabela}")'
            ).fetchall()

            if any(
                referencia[2] == "horario_atendimento" for referencia in referencias
            ):
                raise RuntimeError(f"A tabela {tabela} depende dos horários.")

        conexao.execute("BEGIN IMMEDIATE")

        conexao.execute("""
            CREATE TABLE horario_atendimento_novo (
                id_horario INTEGER PRIMARY KEY AUTOINCREMENT,
                id_profissional INTEGER NOT NULL,
                dia_semana INTEGER NOT NULL
                    CHECK (dia_semana BETWEEN 0 AND 6),
                hora_inicio TEXT NOT NULL,
                hora_fim TEXT NOT NULL,
                CHECK (hora_inicio < hora_fim),
                FOREIGN KEY (id_profissional)
                    REFERENCES profissional(id_profissional)
            )
        """)

        conexao.execute("DROP TABLE horario_atendimento")

        conexao.execute("""
            ALTER TABLE horario_atendimento_novo
            RENAME TO horario_atendimento
        """)

        erros = conexao.execute("PRAGMA foreign_key_check").fetchall()

        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]

        if erros or integridade != "ok":
            raise RuntimeError(f"Falha de integridade: {erros}, {integridade}")

        conexao.commit()
        print("Migração dos horários concluída com sucesso!")

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


if __name__ == "__main__":
    migrar()
