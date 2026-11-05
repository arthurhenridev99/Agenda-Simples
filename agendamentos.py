import re
import secrets
from datetime import date, datetime, timedelta
from notificacoes import registrar_notificacao
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

        cursor = conexao.execute(
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

        id_agendamento = cursor.lastrowid

        registrar_notificacao(
            conexao,
            id_agendamento,
            "novo_agendamento",
        )

        conexao.commit()
        return codigo

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


# Reagendar um atendimento existente
def reagendar_agendamento(id_agendamento, data_nova, hora_nova):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_nova):
        raise ValueError("Data inválida.")

    try:
        data_escolhida = date.fromisoformat(data_nova)
    except ValueError:
        raise ValueError("Data inválida.") from None

    formato_hora = r"(?:[01]\d|2[0-3]):[0-5]\d"

    if not re.fullmatch(formato_hora, hora_nova):
        raise ValueError("Horário inválido.")

    conexao = conectar()

    try:
        # Impedir alterações concorrentes
        conexao.execute("BEGIN IMMEDIATE")

        agendamento = conexao.execute(
            """
            SELECT
                id_servico,
                data,
                hora,
                status,
                duracao_minutos
            FROM agendamento
            WHERE id_agendamento = ?
            """,
            (id_agendamento,),
        ).fetchone()

        if agendamento is None:
            raise ValueError("Agendamento não encontrado.")

        id_servico, data_atual, hora_atual, status, duracao = agendamento

        if status != "agendado":
            raise ValueError("Este agendamento não está ativo.")

        # Verificar o prazo da reserva original
        data_hora_atual = datetime.strptime(
            f"{data_atual} {hora_atual}",
            "%Y-%m-%d %H:%M",
        )

        antecedencia_minima = datetime.now() + timedelta(hours=4)

        if data_hora_atual < antecedencia_minima:
            raise ValueError(
                "O reagendamento exige pelo menos 4 horas " "de antecedência."
            )

        if data_nova == data_atual and hora_nova == hora_atual:
            raise ValueError("Escolha uma data ou horário diferente.")

        # Conferir novamente a disponibilidade
        horarios_disponiveis = calcular_horarios_disponiveis(
            id_servico,
            data_nova,
            id_agendamento_ignorar=id_agendamento,
            duracao_override=duracao,
        )

        if hora_nova not in horarios_disponiveis:
            raise ValueError("O novo horário não está disponível.")

        # Atualizar a reserva mantendo o mesmo código
        cursor = conexao.execute(
            """
            UPDATE agendamento
            SET data = ?, hora = ?
            WHERE id_agendamento = ?
              AND status = 'agendado'
            """,
            (data_nova, hora_nova, id_agendamento),
        )

        if cursor.rowcount != 1:
            raise ValueError("Não foi possível reagendar o atendimento.")

        registrar_notificacao(
            conexao,
            id_agendamento,
            "reagendamento",
        )

        conexao.commit()
        return True

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()
