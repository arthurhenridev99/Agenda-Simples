from pathlib import Path
from database import conectar

BASE_DIR = Path(__file__).resolve().parent
BACKUP = BASE_DIR / "agendamento_backup_pre_feedback.db"


def migrar():
    if not BACKUP.is_file():
        raise RuntimeError("Backup não encontrado. Migração cancelada.")

    conexao = conectar()

    try:
        # Conferir se não existem registros relacionados.
        agendamentos = conexao.execute("SELECT COUNT(*) FROM agendamento").fetchone()[0]

        notificacoes = conexao.execute("SELECT COUNT(*) FROM notificacao").fetchone()[0]

        if agendamentos != 0 or notificacoes != 0:
            raise RuntimeError("Existem registros relacionados. Migração cancelada.")

        # Desabilitar temporariamente as chaves estrangeiras
        # antes de iniciar a transação de reconstrução.
        conexao.execute("PRAGMA foreign_keys = OFF")
        conexao.execute("BEGIN IMMEDIATE")

        # Criar a tabela com as regras definitivas.
        conexao.execute("""
            CREATE TABLE agendamento_novo (
                id_agendamento INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER NOT NULL,
                id_servico INTEGER NOT NULL,
                data TEXT NOT NULL,
                hora TEXT NOT NULL,
                codigo_atendimento TEXT NOT NULL UNIQUE,

                status TEXT NOT NULL DEFAULT 'agendado'
                    CHECK (
                        status IN (
                            'agendado',
                            'cancelado',
                            'concluido',
                            'falta'
                        )
                    ),

                duracao_minutos INTEGER NOT NULL
                    CHECK (duracao_minutos > 0),

                preco_praticado REAL NOT NULL
                    CHECK (preco_praticado >= 0),

                FOREIGN KEY (id_cliente)
                    REFERENCES cliente(id_cliente),

                FOREIGN KEY (id_servico)
                    REFERENCES servico(id_servico)
            )
        """)

        # Substituir somente a tabela vazia.
        conexao.execute("DROP TABLE agendamento")

        conexao.execute("""
            ALTER TABLE agendamento_novo
            RENAME TO agendamento
        """)

        # Conferir a integridade antes de confirmar.
        erros = conexao.execute("PRAGMA foreign_key_check").fetchall()

        if erros:
            raise RuntimeError(f"Erro de integridade encontrado: {erros}")

        integridade = conexao.execute("PRAGMA integrity_check").fetchone()[0]

        if integridade != "ok":
            raise RuntimeError(f"Falha de integridade: {integridade}")

        conexao.commit()
        print("Restrições do banco atualizadas com sucesso!")

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.execute("PRAGMA foreign_keys = ON")
        conexao.close()


if __name__ == "__main__":
    migrar()
