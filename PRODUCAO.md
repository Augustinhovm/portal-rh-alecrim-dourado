# Portal RH V8.0 — Produção

A V8.0 separa o uso de desenvolvimento/local do uso oficial em produção.

## O que mudou

- `debug` não é mais ligado automaticamente.
- Entrada WSGI em `wsgi.py`.
- Gunicorn para hospedagem Linux e Waitress para Windows.
- Suporte a PostgreSQL via `DATABASE_URL`.
- `SECRET_KEY` obrigatória quando `APP_ENV=production`.
- Cookies `Secure`, `HttpOnly` e `SameSite=Lax` em produção.
- Proteção CSRF para formulários POST.
- Cabeçalhos HTTP de segurança e HSTS quando HTTPS estiver ativo.
- Limite configurável de upload.
- Endpoint `/health` para a hospedagem verificar se o serviço está ativo.
- Bloqueio temporário após repetidas tentativas inválidas de login.
- Utilitário de backup para a instalação local.
- `render.yaml` para facilitar uma futura publicação no Render.

## Antes de publicar

1. Preserve sempre `instance` e `app/uploads`.
2. Faça um backup com `backup_windows.bat`.
3. Não envie `.env` real para repositórios.
4. Gere uma `SECRET_KEY` exclusiva para produção.
5. Para uso online permanente, use PostgreSQL e armazenamento persistente para uploads.
6. O banco SQLite de testes não é migrado automaticamente para PostgreSQL nesta versão. A migração dos dados deve ser feita em uma etapa controlada antes da abertura aos colaboradores.

## Desenvolvimento local

Use:

    .\iniciar_windows.bat

O servidor local continua disponível para testes.

## Teste do servidor WSGI no Windows

Crie um `.env` apropriado e execute:

    .\iniciar_producao_windows.bat

O Waitress ouvirá na porta 8000.

## Render

O pacote contém `render.yaml`. A publicação ainda exige criar/conectar o serviço no Render e definir um armazenamento persistente para os anexos.

O comando de produção usado no Linux é:

    gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app

## Backup local

Execute:

    .\backup_windows.bat

Os backups são criados em `backups/AAAAmmdd-HHMMSS/`.

## Observação sobre anexos

Serviços de hospedagem podem apagar arquivos gravados no disco efêmero após reinícios/deploys. A pasta indicada por `UPLOAD_FOLDER` deve estar em disco persistente ou, numa etapa posterior, ser substituída por armazenamento de objetos.

## Próxima etapa de implantação

Antes de liberar o endereço aos colaboradores:
- publicar ambiente de homologação;
- migrar/cadastrar dados;
- testar RH e um colaborador piloto;
- validar ponto, atestados, banco de horas, férias e PDFs;
- configurar domínio e HTTPS;
- só então abrir aos demais colaboradores.
