from datetime import date, datetime, time, timedelta

from database import conectar, atualizar_bloqueios_semanais


def converter_minutos(horario):
    horas, minutos = map(int, horario.split(":"))
    return horas * 60 + minutos


def calcular_horarios_disponiveis(
    id_servico,
    data_texto,
    id_agendamento_ignorar=None,
    duracao_override=None,
):
    data_escolhida = date.fromisoformat(data_texto)
    agora = datetime.now()

    if data_escolhida < agora.date():
        return []

    conexao = conectar()

    try:
        # Buscar somente serviços ativos
        servico = conexao.execute(
            """
            SELECT id_profissional, duracao
            FROM servico
            WHERE id_servico = ? AND ativo = 1
            """,
            (id_servico,),
        ).fetchone()

        if servico is None:
            return []

        id_profissional, duracao = servico

        if duracao_override is not None:
            if duracao_override <= 0:
                return []
            duracao = duracao_override

        # Python: segunda=0, terça=1, ..., domingo=6
        periodos = conexao.execute(
            """
            SELECT hora_inicio, hora_fim
            FROM horario_atendimento
            WHERE id_profissional = ?
              AND dia_semana = ?
            ORDER BY hora_inicio
            """,
            (id_profissional, data_escolhida.weekday()),
        ).fetchall()

        atualizar_bloqueios_semanais(conexao)
        bloqueios = conexao.execute(
            """
            SELECT hora_inicio, hora_fim
            FROM bloqueio
            WHERE id_profissional = ?
              AND (dia_semana = ? OR (dia_semana IS NULL AND data = ?))
            """,
            (id_profissional, data_escolhida.weekday(), data_texto),
        ).fetchall()

        # Considerar a duração salva na época da reserva
        agendamentos = conexao.execute(
            """
            SELECT
                a.id_agendamento,
                a.hora,
                a.duracao_minutos
            FROM agendamento AS a
            JOIN servico AS s
              ON s.id_servico = a.id_servico
            WHERE s.id_profissional = ?
              AND a.data = ?
              AND a.status = 'agendado'
            """,
            (id_profissional, data_texto),
        ).fetchall()

    finally:
        conexao.close()

    # Reunir todos os períodos indisponíveis
    ocupados = [
        (converter_minutos(inicio), converter_minutos(fim)) for inicio, fim in bloqueios
    ]

    for id_agendamento, hora, duracao_reservada in agendamentos:
        if id_agendamento == id_agendamento_ignorar:
            continue

        inicio = converter_minutos(hora)
        ocupados.append((inicio, inicio + duracao_reservada))

    horarios_disponiveis = set()
    antecedencia_minima = agora + timedelta(hours=4)

    for hora_inicio, hora_fim in periodos:
        inicio_periodo = converter_minutos(hora_inicio)
        fim_periodo = converter_minutos(hora_fim)

        # Alinhar os inícios aos intervalos de 30 minutos
        primeiro_inicio = ((inicio_periodo + 29) // 30) * 30

        for inicio in range(
            primeiro_inicio,
            fim_periodo - duracao + 1,
            30,
        ):
            fim = inicio + duracao

            data_hora_inicio = datetime.combine(
                data_escolhida,
                time(inicio // 60, inicio % 60),
            )

            # Exigir pelo menos 4 horas de antecedência
            if data_hora_inicio < antecedencia_minima:
                continue

            # Verificar se há sobreposição
            conflito = any(
                inicio < fim_ocupado and fim > inicio_ocupado
                for inicio_ocupado, fim_ocupado in ocupados
            )

            if not conflito:
                horarios_disponiveis.add(f"{inicio // 60:02d}:{inicio % 60:02d}")

    return sorted(horarios_disponiveis)
