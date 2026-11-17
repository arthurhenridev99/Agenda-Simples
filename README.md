# AgendaSimples 💅

**Sistema web de agendamento de manicure e pedicure**, desenvolvido como projeto acadêmico PTDS, com interface responsiva para clientes e profissionais.

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-banco%20de%20dados-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Status](https://img.shields.io/badge/status-projeto%20acad%C3%AAmico%20finalizado-2E8B57)](#validacao-do-projeto)

> Repositório técnico: `PTDS-Agendamento` · Nome apresentado no sistema: **AgendaSimples**.

## Visão geral

O AgendaSimples organiza a rotina de atendimentos de manicure e pedicure. Clientes consultam a disponibilidade, fazem reservas e acompanham agendamentos por código e telefone. A profissional gerencia serviços, horários, bloqueios, agenda, histórico e notificações internas.

A identidade visual utiliza tons de roxo e lilás, cartões arredondados e layouts adaptáveis a celulares e computadores.

## Funcionalidades

### Para clientes
- Consultar serviços e horários disponíveis.
- Agendar um atendimento informando nome e telefone.
- Receber um código único de identificação da reserva.
- Consultar, cancelar e reagendar reservas mediante validação dos dados.
- Respeitar a antecedência mínima de quatro horas nas operações aplicáveis.

### Para profissionais
- Criar conta, entrar e sair da área administrativa.
- Configurar informações do estabelecimento.
- Cadastrar, editar e ativar/desativar serviços.
- Definir horários de trabalho e bloqueios de agenda.
- Visualizar o painel e a agenda de atendimentos.
- Registrar atendimentos como concluídos ou faltas, conforme as regras de horário.
- Consultar histórico e notificações internas.

## Tecnologias

| Camada | Tecnologia |
| --- | --- |
| Backend | Python e Flask 3.1.3 |
| Interface | HTML, CSS, JavaScript e Jinja2 |
| Banco de dados | SQLite |
| Servidor de produção | Gunicorn |
| Hospedagem utilizada | Railway |

As dependências exatas estão em [`requirements.txt`](requirements.txt).

## Executar localmente

**Pré-requisito:** Python 3 instalado.

1. Clone o repositório e acesse a pasta:

   ```bash
   git clone https://github.com/arthurhenridev99/PTDS-Agendamento.git
   cd PTDS-Agendamento
   ```

2. Crie e ative um ambiente virtual no Windows:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate
   ```

   No Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`.

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

4. Defina uma chave de sessão estável para o ambiente:

   **Windows (CMD):**
   ```bat
   set "FLASK_SECRET_KEY=substitua-por-um-segredo-aleatorio-forte"
   ```

   **Linux/macOS:**
   ```bash
   export FLASK_SECRET_KEY="substitua-por-um-segredo-aleatorio-forte"
   ```

   Gere um segredo com `python -c "import secrets; print(secrets.token_hex(32))"` e não o publique.

5. Inicie a aplicação:

   ```bash
   python wsgi.py
   ```

   **Atenção:** `wsgi.py` prepara o banco, mas não inicia um servidor HTTP por conta própria. Para acessar o sistema localmente, use:

   ```bash
   flask --app wsgi:app run
   ```

   Abra **http://127.0.0.1:5000**.

O SQLite é inicializado pela entrada WSGI. Sem `DATABASE_PATH`, o arquivo `agendamento.db` fica na raiz do projeto e é ignorado pelo Git.

## Configuração de produção

Configure as variáveis de ambiente no serviço de hospedagem, sem registrar seus valores no repositório:

| Variável | Finalidade |
| --- | --- |
| `FLASK_SECRET_KEY` | Chave estável de assinatura das sessões |
| `DATABASE_PATH` | Caminho do banco SQLite em armazenamento persistente |
| `TZ` | Fuso horário do processo; para Brasília, `America/Sao_Paulo` |

Exemplo de comando de inicialização:

```bash
gunicorn --workers 1 wsgi:app
```

**Importante:** confirme o volume persistente e o fuso horário efetivo do ambiente. O código utiliza o horário local do processo para algumas regras de antecedência. A presença da variável `TZ` não substitui a verificação prática do relógio do servidor.

## Estrutura principal

```text
.
├── app.py                    # Rotas, sessões e regras da aplicação web
├── agendamentos.py           # Operações de agendamento
├── disponibilidade.py        # Cálculo dos horários disponíveis
├── database.py               # Conexão, esquema e inicialização SQLite
├── notificacoes.py           # Notificações internas
├── recuperacao.py            # Infraestrutura opcional de recuperação por e-mail
├── wsgi.py                   # Entrada para Gunicorn / Flask
├── requirements.txt
├── static/
│   ├── css/style.css
│   ├── img/
│   └── js/
└── templates/                # Páginas Jinja2
```

## Validação do projeto

Na revisão final, foram **aprovados manualmente 13 requisitos funcionais e 7 não funcionais** pelo responsável pelo projeto. Também foram relatados como aprovados os testes de reservas simultâneas e de persistência dos dados após deploy.

Esses resultados representam **validação manual informada**, não uma garantia de cobertura automatizada completa ou de ausência de falhas. A configuração do fuso horário em produção deve ser conferida separadamente.

## Funcionalidades previstas para versões futuras

- **Recuperação de senha por e-mail** e **recuperação de código por WhatsApp**: não fazem parte da entrega operacional atual. Existem rotas e código preparatório no repositório, mas integrações externas não foram configuradas como funcionalidades ativas.
- **Backup externo automatizado**: não implantado. O repositório contém um utilitário administrativo opcional e orientações em [`BACKUP_RESTAURACAO.md`](BACKUP_RESTAURACAO.md); sua presença não significa que existam cópias externas.

## Documentação complementar

- [Reformulação da interface](RELATORIO_INTERFACE.md)
- [Cadastro e infraestrutura opcional de recuperação](RECUPERACAO_DE_SENHA.md)
- [Backup e restauração (procedimento não implantado)](BACKUP_RESTAURACAO.md)

## Segurança e privacidade

- Senhas são armazenadas como hashes.
- Formulários sensíveis usam tokens CSRF.
- Sessões possuem atributos de segurança e validade configurada.
- O banco SQLite, credenciais e arquivos `.env` não devem ser enviados ao GitHub.
- Dados pessoais de clientes e profissionais devem ser tratados com acesso restrito.

---

**AgendaSimples** — seu autocuidado começa aqui.
