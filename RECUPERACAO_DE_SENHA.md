# AgendaSimples — cadastro e recuperação

Alterações restritas à identidade, cadastro e recuperação de senha na branch `Finalizando-Navegação`.

## Cadastro

Novas contas usam nome, e-mail, WhatsApp com DDD, senha e confirmação. A existência de outra profissional não bloqueia mais o cadastro. O e-mail é armazenado no campo `profissional.login`, com verificação de duplicidade sem diferenciar maiúsculas/minúsculas. Contas antigas mantêm login, senha e dados.

A coluna `profissional.whatsapp` é adicionada de forma automática, sem apagar registros, ao abrir `/cadastro` ou executar `py database.py`. Não execute as migrações antigas para esta alteração.

## Recuperação completa

Login → Esqueci minha senha → e-mail cadastrado → mensagem com link → nova senha → login.

O link expira em 30 minutos e perde a validade quando a senha é alterada. Os formulários têm proteção CSRF. Solicitações usam resposta genérica para não revelar contas cadastradas e intervalo mínimo de um minuto por sessão. O envio usa SMTP autenticado com TLS; não há senha ou token exibido na página.

### Configuração necessária no computador/servidor

Antes de iniciar `py app.py`, configure as seguintes variáveis de ambiente com os dados do seu provedor. Não grave credenciais no repositório nem envie sua senha neste chat.

| Variável | Valor |
| --- | --- |
| `FLASK_SECRET_KEY` | Segredo aleatório fixo, mantido entre reinicializações |
| `SMTP_HOST` | Servidor SMTP do provedor |
| `SMTP_PORT` | `587` para STARTTLS ou `465` para TLS direto |
| `SMTP_USER` | Usuário autorizado pelo provedor |
| `SMTP_PASSWORD` | Credencial SMTP ou senha de aplicativo fornecida pelo provedor |
| `SMTP_FROM` | E-mail remetente autorizado |
| `APP_BASE_URL` | `http://127.0.0.1:5000` em teste local; URL HTTPS na hospedagem |

No CMD, cada variável é definida com `set "NOME=valor"` na mesma janela em que a aplicação será iniciada. Para gerar o segredo, execute `py -c "import secrets; print(secrets.token_hex(32))"` uma vez e guarde o resultado de forma segura. Alterar esse segredo invalida sessões e links pendentes.

O endereço local do link só abre no computador onde o sistema está rodando. Para uso externo, configure a URL HTTPS real. Sem configuração de e-mail, o formulário informa indisponibilidade; ele não simula envio bem-sucedido. Em caso de falha SMTP, o servidor registra uma mensagem de erro sem credenciais e a resposta pública permanece genérica.

Contas antigas cujo login não é um e-mail continuam acessando normalmente, mas não possuem endereço de recuperação. Nenhum endereço foi inventado ou vinculado automaticamente a essas contas.

## Testes

`py teste_contas.py`: oito testes com SQLite temporário e SMTP simulado cobrem cadastro de duas contas, duplicidade, validações, migração de conta antiga, login, recuperação, CSRF, confirmação da nova senha, link expirado/adulterado/reutilizado, endereço desconhecido, intervalo de solicitação, ausência/falha de SMTP e envio com TLS.

Também foram executados os testes existentes de interface, antecedência, notificações, situações e visualização de notificações. Envio real depende da configuração acima; não foram enviados e-mails durante os testes. Validação visual em navegador permanece pendente neste ambiente.
