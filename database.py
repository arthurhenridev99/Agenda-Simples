import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "agendamento.db"


def conectar():
    conexao = sqlite3.connect(DATABASE)
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def atualizar_cadastro_profissional(conexao):
    """Migração aditiva: preserva contas e dados de bancos já existentes."""
    conexao.execute("BEGIN IMMEDIATE")
    try:
        colunas = {linha[1] for linha in conexao.execute("PRAGMA table_info(profissional)")}
        if "whatsapp" not in colunas:
            conexao.execute("ALTER TABLE profissional ADD COLUMN whatsapp TEXT NOT NULL DEFAULT ''")
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise


def inicializar_banco():
    with conectar() as conexao:

        # Tabela 1 - Profissional
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS profissional (
                id_profissional INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                login TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL
            )
        """)

        atualizar_cadastro_profissional(conexao)

        # Tabela 2 - Servicos
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS servico (
                id_servico INTEGER PRIMARY KEY AUTOINCREMENT,
                id_profissional INTEGER NOT NULL,
                nome TEXT NOT NULL,
                preco REAL NOT NULL CHECK (preco >= 0),
                duracao INTEGER NOT NULL CHECK (duracao > 0),
                ativo INTEGER NOT NULL DEFAULT 1
                    CHECK (ativo IN (0, 1)),
                FOREIGN KEY (id_profissional)
                    REFERENCES profissional(id_profissional)
            )
        """)

        # Tabela 3 - Horarios de atendimento
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS horario_atendimento (
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

        # Tabela 4 - Bloqueios
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS bloqueio (
                id_bloqueio INTEGER PRIMARY KEY AUTOINCREMENT,
                id_profissional INTEGER NOT NULL,
                data TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fim TEXT NOT NULL,
                FOREIGN KEY (id_profissional)
                    REFERENCES profissional(id_profissional)
            )
        """)

        # Tabela 5 - Clientes
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS cliente (
                id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                telefone TEXT NOT NULL
            )
        """)

        # Tabela 6 - Agendamentos
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS agendamento (
                id_agendamento INTEGER PRIMARY KEY AUTOINCREMENT,
                id_cliente INTEGER NOT NULL,
                id_servico INTEGER NOT NULL,
                data TEXT NOT NULL,
                hora TEXT NOT NULL,
                codigo_atendimento TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'agendado'
                    CHECK (status IN (
                        'agendado',
                        'cancelado',
                        'concluido',
                        'falta'
                    )),
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

        # Tabela 7 - Notificacoes
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS notificacao (
                id_notificacao INTEGER PRIMARY KEY AUTOINCREMENT,
                id_agendamento INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                visualizada INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (id_agendamento)
                    REFERENCES agendamento(id_agendamento)
            )
        """)

    print("Todas as 7 tabelas foram inicializadas com sucesso!")


if __name__ == "__main__":
    inicializar_banco()



def concluir_agendamentos_vencidos(agora=None):
    """Conclui atendimentos ativos cujo horário de término já passou.

    Usa a duração registrada no agendamento, não a duração atual do serviço.
    Preserva cancelamentos, faltas e conclusões existentes.
    """
    from datetime import datetime

    instante = agora or datetime.now()
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            UPDATE agendamento
               SET status = 'concluido'
             WHERE status = 'agendado'
               AND datetime(
                   data || ' ' || hora,
                   '+' || duracao_minutos || ' minutes'
               ) <= datetime(?)
            """,
            (instante.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        return cursor.rowcount
