from datetime import datetime

# Tipos de notificacao permitidos
TIPOS_NOTIFICACAO = {
    "novo_agendamento",
    "cancelamento",
    "reagendamento",
    "conclusao",
    "falta",
}


def registrar_notificacao(conexao, id_agendamento, tipo):
    """
    Registra uma notificacao na mesma transacao
    da operacao que a originou.
    """

    if tipo not in TIPOS_NOTIFICACAO:
        raise ValueError("Tipo de notificação inválido.")

    data_hora = datetime.now().isoformat(timespec="seconds")

    conexao.execute(
        """
        INSERT INTO notificacao (
            id_agendamento,
            tipo,
            data_hora,
            visualizada
        )
        VALUES (?, ?, ?, 0)
        """,
        (id_agendamento, tipo, data_hora),
    )
