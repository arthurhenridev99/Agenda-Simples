# Backup e restauração — AgendaSimples

Este procedimento é **administrativo**, executado em terminal com acesso ao volume. Não cria rota HTTP, não envia arquivos por e-mail e não modifica o banco de produção durante o backup.

## 1. Criar backup

O sistema usa `DATABASE_PATH` (por exemplo, `/data/agendamento.db`) quando configurado; caso contrário, usa o arquivo local padrão. No ambiente com acesso ao banco:

```bash
python backup_sqlite.py backup --destino /caminho/externo/agendamento-AAAA-MM-DD-HHMM.db
python backup_sqlite.py verificar --arquivo /caminho/externo/agendamento-AAAA-MM-DD-HHMM.db
```

Crie a pasta de destino antes. O script recusa sobrescrever arquivos e verifica a integridade e as tabelas essenciais. Use um nome novo em cada execução. **O diretório de destino deve estar fora do volume da aplicação e os arquivos precisam ser copiados para armazenamento externo protegido.** Não adicione backups ao GitHub: contêm informações pessoais.

O backup é consistente mesmo com leituras/escritas concorrentes, pois utiliza `sqlite3.Connection.backup`. A ferramenta **não agenda** backups nem os transfere automaticamente. Defina uma rotina operacional e confirme periodicamente que cópias externas podem ser recuperadas.

## 2. Restauração — procedimento manual e controlado

1. Identifique o backup correto e valide-o com `python backup_sqlite.py verificar --arquivo ARQUIVO.db`.
2. Programe uma janela de manutenção e **pare todas as instâncias e processos** que acessam o banco, incluindo workers do Gunicorn. Não restaure com a aplicação ativa.
3. Preserve uma cópia de segurança do banco atual, mesmo que esteja com problemas. Guarde-a fora do volume.
4. Com o serviço parado, substitua o arquivo apontado por `DATABASE_PATH` pela cópia validada. Preserve permissões e proprietário adequados. Se houver arquivos `-wal` e `-shm` associados ao banco anterior, trate-os somente com o serviço totalmente parado, após garantir a cópia de segurança, para não misturar estados.
5. Inicie o serviço e confirme login, serviços, clientes e agendamentos. Valide a integridade novamente e monitore os logs.

**A restauração reverte o banco ao momento do backup:** alterações posteriores serão perdidas. Faça primeiro um teste em ambiente isolado, nunca diretamente na produção. Não execute o script de backup como rotina de inicialização do Gunicorn: ele é um comando administrativo.

## 3. Railway

O deploy por GitHub não executa este script automaticamente. É necessário acesso autorizado ao arquivo do volume persistente para criar e exportar o backup. Se o ambiente não permitir acesso/exportação ao volume, configure primeiro uma solução de backup externa apropriada; não considere o sistema protegido só porque os dados sobrevivem a deploys. Nenhuma variável privada precisa ser exibida ou modificada para adicionar estes arquivos ao repositório.
