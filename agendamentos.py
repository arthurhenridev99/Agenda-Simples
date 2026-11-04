import re
import secrets
from datetime import date

from database import conectar
from disponibilidade import calcular_horarios_disponiveis


def registrar_agendamento(
    id_servico,
    data_texto,
    hora,
    nome_cliente,
    telefone_cliente,
):
    nome = nome_cliente.strip()
    telefone = re.sub(r"\D", "", telefone_cliente)

    if not 3 <= len(nome) <= 100:
        raise ValueError("Informe o nome completo da cliente.")

    if len(telefone) not in (10, 11):
        raise ValueError("Informe um telefone válido com DDD.")

    try:
        data_escolhida = date.fromisoformat(data_texto)

        if data_escolhida.isoformat() != data_texto:
            raise ValueError

    except ValueError:
        raise ValueError("Data inválida.") from None

    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hora):
        raise ValueError("Horário inválido.")

    conexao = conectar()

    try:
        # Impede que duas reservas sejam gravadas ao mesmo tempo.
        conexao.execute("BEGIN IMMEDIATE")

        servico = conexao.execute(
            """
            SELECT duracao, preco
            FROM servico
            WHERE id_servico = ? AND ativo = 1
            """,
            (id_servico,),
        ).fetchone()

        if servico is None:
            raise ValueError("Este serviço não está disponível.")

        # Revalidar o horário antes de salvar.
        disponiveis = calcular_horarios_disponiveis(
            id_servico,
            data_texto,
        )

        if hora not in disponiveis:
            raise ValueError("Este horário não está mais disponível. Escolha outro.")

        # Evitar duplicar clientes com o mesmo telefone.
        cliente = conexao.execute(
            """
            SELECT id_cliente
            FROM cliente
            WHERE telefone = ?
            ORDER BY id_cliente
            LIMIT 1
            """,
            (telefone,),
        ).fetchone()

        if cliente:
            id_cliente = cliente[0]
        else:
            cursor = conexao.execute(
                """
                INSERT INTO cliente (nome, telefone)
                VALUES (?, ?)
                """,
                (nome, telefone),
            )
            id_cliente = cursor.lastrowid

        # Código único para consulta da reserva.
        codigo = secrets.token_hex(8).upper()

        conexao.execute(
            """
            INSERT INTO agendamento (
                id_cliente,
                id_servico,
                data,
                hora,
                codigo_atendimento,
                status,
                duracao_minutos,
                preco_praticado
            )
            VALUES (?, ?, ?, ?, ?, 'agendado', ?, ?)
            """,
            (
                id_cliente,
                id_servico,
                data_texto,
                hora,
                codigo,
                servico[0],
                servico[1],
            ),
        )

        conexao.commit()
        return codigo

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()
