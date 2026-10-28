
from database import conectar


def coluna_existe(conexao, tabela, coluna):
    colunas = conexao.execute(
        f"PRAGMA table_info({tabela})"
    ).fetchall()

    return any(item[1] == coluna for item in colunas)


def migrar():
    with conectar() as conexao:

        if not coluna_existe(
            conexao, "agendamento", "duracao_minutos"
        ):
            conexao.execute("""
                ALTER TABLE agendamento
                ADD COLUMN duracao_minutos INTEGER
                CHECK (duracao_minutos > 0)
            """)

        if not coluna_existe(
            conexao, "agendamento", "preco_praticado"
        ):
            conexao.execute("""
                ALTER TABLE agendamento
                ADD COLUMN preco_praticado REAL
                CHECK (preco_praticado >= 0)
            """)

        if not coluna_existe(
            conexao, "servico", "ativo"
        ):
            conexao.execute("""
                ALTER TABLE servico
                ADD COLUMN ativo INTEGER NOT NULL DEFAULT 1
                CHECK (ativo IN (0, 1))
            """)

    print("Atualização do banco concluída com sucesso!")


if __name__ == "__main__":
    migrar()
