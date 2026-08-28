# Segurança — Portal RH Alecrim Dourado V8.5

Esta versão aplica hardening defensivo à aplicação Flask. Nenhum sistema conectado à internet pode ser considerado invulnerável; as medidas abaixo reduzem significativamente riscos comuns e devem ser combinadas com manutenção, backups, atualizações e controle de acesso.

## Proteções implementadas

- CSRF obrigatório em todas as requisições POST.
- Verificação adicional de Origin em produção.
- Sessões com cookie HttpOnly, Secure em produção e prefixo `__Host-`.
- Rotação da sessão após autenticação para mitigar session fixation.
- HSTS em produção.
- Content-Security-Policy com JavaScript somente da própria aplicação.
- Bloqueio de iframe (`frame-ancestors 'none'` e `X-Frame-Options: DENY`).
- `nosniff`, política de referência restritiva e políticas de recursos cross-origin.
- Respostas autenticadas e documentos com `Cache-Control: no-store`.
- Limitação persistente de tentativas de login no PostgreSQL.
- Limitação persistente de tentativas do PIN de ponto/assinatura.
- Mensagem única para usuário/senha incorretos e verificação de hash dummy para reduzir enumeração por tempo.
- Política de senha pessoal: mínimo de 10 caracteres, com maiúscula, minúscula, número e caractere especial.
- Uploads aceitos somente nos formatos permitidos.
- PDFs validados pela assinatura `%PDF-` e pelo parser antes de serem gravados.
- Imagens efetivamente decodificadas e verificadas, impedindo extensões falsas simples.
- Limite de dimensão para imagens e limite global de upload.
- Arquivos recebem nomes internos aleatórios, sem confiar no nome fornecido pelo usuário.
- Permissão de arquivo `0600` aplicada quando suportada pelo sistema operacional.
- Atestados e holerites continuam protegidos por autorização de usuário antes do download.
- Auditoria registra operações relevantes.
- Erros 400/403/404/500 não exibem traceback interno ao usuário em produção.

## Configuração obrigatória no Render

- `APP_ENV=production`
- `SECRET_KEY`: valor aleatório gerado pelo Render; nunca salvar no GitHub.
- `DATABASE_URL`: PostgreSQL privado do Render.
- `UPLOAD_FOLDER`: deve apontar para armazenamento persistente.
- `MAX_UPLOAD_MB`: limite máximo de cada requisição.
- `SESSION_MINUTES`: duração máxima configurada da sessão.

## Recomendações operacionais

1. Não utilizar contas compartilhadas de RH.
2. Desativar imediatamente usuários desligados.
3. Não reutilizar senhas provisórias.
4. Revisar periodicamente a tela de Auditoria.
5. Manter dependências Python atualizadas após testes em homologação.
6. Fazer backup do PostgreSQL e do armazenamento de documentos.
7. Utilizar autenticação multifator na conta Render e na conta GitHub.
8. Manter o repositório GitHub privado.
9. Não armazenar `.env`, banco SQLite, uploads, backups ou chaves no Git.
10. Em caso de suspeita de vazamento, trocar imediatamente `SECRET_KEY`, credenciais administrativas e tokens de infraestrutura.

## Limites

A versão não inclui WAF/CDN, antivírus de arquivos, MFA dentro do próprio Portal, SSO corporativo ou análise automática de vulnerabilidades externas. Esses componentes podem ser adicionados em uma etapa posterior.
