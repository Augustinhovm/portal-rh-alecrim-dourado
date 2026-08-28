# Portal RH — Associação

MVP funcional para cadastro de colaboradores, ponto, atestados, banco de horas, horas extras, aprovações, documentos e auditoria.

## Recursos
- Perfis: RH/Administrador, Responsável de Área e Colaborador.
- Cadastro e prontuário digital de colaboradores.
- Registro sequencial de ponto (entrada, saída intervalo, retorno, saída).
- Solicitação de correção de ponto com aprovação.
- Envio de atestados pelo próprio colaborador.
- Atestados visíveis somente ao titular e ao RH; gestores não abrem conteúdo médico.
- Solicitação e aprovação de uso de banco de horas.
- Solicitação e aprovação de horas extras.
- Atualização automática do saldo após aprovação.
- Central de aprovações para RH e responsáveis.
- Documentos funcionais anexados pelo RH.
- Relatório de ponto em XLSX.
- Log de auditoria.

## Instalação local

1. Instale Python 3.11 ou superior.
2. Crie um ambiente virtual:
   - Windows: `python -m venv .venv && .venv\\Scripts\\activate`
   - Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`
3. Instale dependências: `pip install -r requirements.txt`
4. Copie `.env.example` para `.env` e altere `SECRET_KEY`.
5. Execute `python seed.py` uma única vez.
6. Execute `python run.py`.
7. Abra `http://127.0.0.1:5000`.

## Usuários de demonstração
- RH: `rh@associacao.local` / `Admin@123`
- Gestor: `gestor@associacao.local` / `Gestor@123`
- Colaborador: `colaborador@associacao.local` / `Colab@123`

Troque todas as senhas antes de uso real.

## Fuso horário oficial
O Portal RH usa **America/Sao_Paulo** como fuso horário oficial em ponto, solicitações, aprovações, documentos e auditoria.

### Atualização da versão 2 para a versão 3
Se você já utilizou a versão anterior, copie os arquivos da versão 3 sobre a pasta atual **sem apagar a pasta `instance`**. Depois:
1. Feche o servidor com `CTRL+C`.
2. Execute `corrigir_fuso_windows.bat` uma única vez.
3. Execute `iniciar_windows.bat`.

O script converte os horários antigos que foram gravados como UTC para o horário de Brasília e cria um marcador para não aplicar a conversão duas vezes.

## Produção
Esta versão é adequada para validação e uso controlado em rede interna. Para disponibilização pública, recomenda-se:
- PostgreSQL em vez de SQLite.
- HTTPS obrigatório.
- armazenamento de anexos privado e criptografado (S3 compatível/Supabase Storage/Azure Blob, por exemplo);
- backups automáticos;
- MFA para RH e responsáveis;
- política de retenção de documentos;
- antivírus/varredura de anexos;
- rate limiting e proteção CSRF;
- e-mail para redefinição de senha;
- revisão jurídica/trabalhista e de privacidade antes de transformar o módulo de ponto em sistema oficial de controle eletrônico de jornada.

## Observação importante sobre ponto
O módulo incluído registra marcações e trilha de auditoria, mas o uso como sistema oficial de registro eletrônico de ponto no Brasil deve ser validado conforme a legislação e as regras trabalhistas aplicáveis à organização. Não trate este MVP como homologação jurídica automática.

## Estrutura
- `app/models.py` — banco de dados.
- `app/rh.py` — fluxos de RH, ponto, documentos e aprovações.
- `app/auth.py` — autenticação.
- `app/templates/` — telas.
- `app/static/css/app.css` — interface responsiva.
- `seed.py` — dados de demonstração.


## Versão 4 - Central de Atestados
- RH/Admin possui menu **Atestados recebidos**.
- Lista todos os atestados enviados pelos colaboradores.
- Permite abrir PDF/imagem em nova aba, filtrar por colaborador/período/status e marcar como Recebido, Conferido, Arquivado ou Devolvido.
- Gestores continuam sem acesso ao conteúdo médico; acesso restrito ao RH/Admin e ao titular.
- `tzdata` incluído nas dependências para Windows.

## Versão 5 — Controle individual pelo RH

No perfil de cada colaborador, o RH/Administrador agora possui:

- saldo individual do banco de horas;
- histórico de solicitações que movimentam o banco;
- ajustes manuais de crédito/débito com justificativa obrigatória;
- consulta das últimas marcações de ponto;
- inclusão de marcação esquecida;
- correção de data, horário e tipo de marcação;
- remoção de registro duplicado/incorreto;
- trilha de auditoria para todas essas ações.

A atualização cria automaticamente a nova tabela de ajustes de banco de horas ao iniciar o sistema. Para preservar dados existentes, não apague `instance/` nem `app/uploads/` ao atualizar.


## V6 - PDF mensal de ponto
Na ficha individual de cada colaborador, o perfil RH/Administrador possui o bloco **Espelho mensal de ponto em PDF**. Escolha a competência e clique em **Baixar PDF mensal**. O arquivo contém os registros de todos os dias do mês e evidencia marcações adicionais e ajustes administrativos. A geração do relatório é registrada na Auditoria.

Após atualizar para a V6, execute `atualizar_v6_windows.bat` uma vez para instalar o ReportLab.

## Versão 6.3 — fechamento mensal no PDF de ponto
O espelho mensal individual agora exibe horas trabalhadas e horas extras aprovadas por dia. Ao final do PDF, há um resumo com horas trabalhadas registradas, horas extras aprovadas, créditos manuais, horas descontadas/uso de banco e saldo mensal.


## Versão 6.4
O colaborador passa a visualizar de forma destacada o próprio saldo de banco de horas na tela inicial, no menu Meu perfil e antes de fazer novas solicitações.


## V6.5 — Banco de horas programado
Solicitações futuras aprovadas de uso de banco ficam reservadas. O débito no saldo realizado ocorre somente na data de uso. O sistema mostra saldo realizado, horas programadas e saldo disponível. Execute `atualizar_v65_windows.bat` uma vez após atualizar, preservando `instance` e `app/uploads`.


## V6.6 — Correção de saldo disponível
Corrige o duplo desconto de utilizações futuras de banco de horas que já haviam sido debitadas nas versões antigas. A migração restaura essas horas ao saldo realizado, mantém-nas como programadas e deixa o débito efetivo para a data de utilização. Execute `atualizar_v66_windows.bat` uma única vez antes de iniciar o sistema.


## V6.7 — Primeiro acesso e senha pessoal
O RH define uma senha provisória ao cadastrar o colaborador. No primeiro login, o usuário é direcionado obrigatoriamente para criar sua senha pessoal e não pode acessar os demais módulos antes da troca. O RH também pode gerar uma nova senha provisória dentro do perfil do colaborador. Usuários já existentes não são forçados a trocar a senha automaticamente. Execute `atualizar_v67_windows.bat` uma vez após atualizar.


## V6.8 — Senha numérica para registro de ponto
Cada colaborador possui uma senha de ponto independente, composta por exatamente 6 dígitos numéricos. O PIN é armazenado somente como hash. Toda marcação feita pelo colaborador exige o PIN correto. O RH define o PIN no cadastro de novos colaboradores e pode redefini-lo no perfil individual. Para colaboradores já existentes, execute `atualizar_v68_windows.bat` e depois defina o PIN pelo acesso do RH.


## V6.8.1 — Correção do campo de senha de ponto
Corrige a tela de Registro de Ponto para exibir o campo obrigatório de PIN numérico de 6 dígitos antes do botão de registro.


## V6.9 — Edição de cadastro e foto
O RH pode editar o cadastro completo de cada colaborador por meio do botão `Editar cadastro` na ficha individual. A mesma tela permite enviar ou substituir a foto do colaborador (JPG, JPEG, PNG ou WEBP). Alterações cadastrais são registradas na Auditoria. Execute `atualizar_v69_windows.bat` uma vez antes de iniciar esta versão.


## V6.9.1 — Foto na bolinha do perfil
A foto cadastrada pelo RH agora aparece no avatar circular do usuário no cabeçalho do Portal RH. Quando não houver foto cadastrada, o sistema exibe a inicial do nome.


## V6.10 — Impressão em lote de atestados
Na Central de Atestados Recebidos, o RH pode selecionar um intervalo de até 30 dias corridos pela data em que o documento foi anexado ao Portal. O sistema gera um único PDF com uma folha de identificação e o arquivo original de cada atestado (PDF ou imagem). Execute `atualizar_v610_windows.bat` uma vez para instalar a dependência `pypdf`.


## V7.0 — Núcleo RH
Inclui cálculo de jornada, central de fechamento mensal, ciência do espelho, extrato de banco de horas, férias no prontuário e central de pendências no dashboard. O cálculo automático usa a jornada padrão cadastrada e considera 1h de intervalo para jornadas superiores a 6h. Revise a jornada individual antes do fechamento oficial.


## V7.1 — Menu lateral por grupos
A navegação superior foi simplificada. O menu completo fica em uma barra lateral recolhível, aberta pelo botão de menu. Os acessos são organizados por grupos: Principal, Ponto e Jornada, Banco de Horas, Saúde e Atestados, Colaboradores, Gestão RH e Administração. Cada perfil continua vendo somente os itens permitidos.


## V7.2 — Ciência vinculada ao relatório mensal
Após o fechamento, o colaborador deve abrir o PDF mensal antes de registrar ciência. O PDF reúne espelho de ponto, resumo mensal e extrato detalhado de créditos/débitos do banco de horas. A abertura do relatório é registrada no sistema e libera o botão de ciência.


## V7.3 — Gestão de férias
Exibe período aquisitivo em andamento, último período concluído, período concessivo, dias adquiridos, utilizados, disponíveis, programados e saldo após programação. O RH pode provisionar férias futuras sem consumir o saldo; quando marcar a programação como realizada, o período passa ao histórico e os dias passam a compor o total utilizado.


## V7.3.1 — Correção cumulativa de banco
O atualizador verifica as estruturas adicionadas nas versões anteriores e cria automaticamente colunas/tabelas ausentes, incluindo `employee_viewed_at`, férias, programação de férias, foto, PIN e campos do banco de horas. Use `atualizar_v731_windows.bat` antes de iniciar.


## V7.3.2 — Data de retorno das férias
A programação de férias agora registra início previsto e retorno previsto. O colaborador visualiza o próximo período programado diretamente na tela inicial, com início, retorno e quantidade de dias. Programações antigas recebem retorno estimado automaticamente com base na data inicial e nos dias cadastrados.


## V7.4 — Identidade Visual Alecrim Dourado
Redesign visual baseado no material institucional da Associação Alecrim Dourado: paleta amarelo-dourado, grafite e branco, linguagem orgânica e uso da marca oficial extraída do material fornecido. A marca aparece no login, cabeçalho e menu lateral. Não há alteração no banco de dados nesta versão.


## V7.5 — Dashboard institucional
A marca Alecrim Dourado foi centralizada na parte superior do portal. O menu lateral recebeu acabamento grafite com destaques dourados, e o conteúdo ganhou espaçamento, cartões e detalhes visuais inspirados no layout de referência aprovado. Nenhuma alteração de banco de dados.


## V7.6 — Nova tela inicial do colaborador
A página inicial foi reconstruída para seguir a referência visual aprovada: banner de boas-vindas, resumo diário, avisos e pendências, férias programadas e extrato resumido do banco de horas. Os valores são alimentados pelos registros reais do Portal RH.


## V7.6.1 — Responsividade mobile
A interface foi adaptada para smartphones e tablets: cabeçalho compacto, logo centralizada, menu lateral otimizado para toque, cards empilhados, formulários em uma coluna, widgets de férias e banco de horas verticais, tabelas com rolagem horizontal e inputs com tamanho adequado para evitar zoom automático em celulares.


## V8.0 — Preparação para produção
A V8.0 adiciona configuração por ambiente, WSGI, suporte a PostgreSQL, proteção CSRF, cookies seguros, cabeçalhos de segurança, limitação básica de tentativas de login, health check, backup local, arquivos de configuração para Render e documentação de implantação. A base SQLite atual permanece preservada e continua funcionando no ambiente local.


## V8.0.1 — Compatibilidade PostgreSQL
Corrige filtros de data que comparavam `DATE` com strings ISO, comportamento tolerado pelo SQLite mas rejeitado pelo PostgreSQL. Os filtros de ponto, dashboard, atestados, banco de horas e relatórios agora utilizam objetos `date` tipados.


## V8.0.2 — Login em tela cheia
Corrige a página de autenticação para ocupar 100% da largura e altura da viewport, sem margens ou faixas externas. Alertas ficam sobrepostos e não deslocam o layout. O comportamento responsivo para tablet e celular foi preservado.


## V8.1 — Holerites mensais
O RH pode selecionar uma competência e enviar vários holerites em PDF de uma vez. O Portal associa automaticamente cada PDF ao colaborador quando o nome completo cadastrado aparece no nome do arquivo, ignorando acentos, caixa, espaços e hífens. Arquivos não associados podem ser enviados manualmente. Cada colaborador visualiza somente os próprios holerites. O sistema registra quando o documento foi visualizado e substitui automaticamente um holerite reenviado para a mesma competência.


## V8.1.1 — Associação pelo conteúdo do PDF
O Portal passa a extrair o texto do próprio holerite e associa o documento ao colaborador quando encontra o nome completo cadastrado. O nome do arquivo não participa da identificação. PDFs sem camada de texto permanecem para associação manual.


## V8.1.2 — PDF consolidado de holerites
O RH envia um único PDF mensal contendo todos os holerites. O Portal analisa cada página, identifica o colaborador pelo nome completo no conteúdo e gera um PDF individual contendo somente as páginas daquele colaborador. Páginas não identificadas não são distribuídas automaticamente.


## V8.1.3 — Correção de entrega de holerites
Reforça o vínculo entre holerite, colaborador e usuário de acesso ao Portal. O colaborador passa a consultar os documentos diretamente pelo `employee_id` associado ao usuário logado. A tela inicial exibe o último holerite e o RH visualiza o e-mail exato do usuário recebedor. Colaboradores identificados no PDF mas sem usuário vinculado são sinalizados e não recebem distribuição automática.


## V8.2 — Fechamento mensal com assinatura eletrônica
O fechamento mensal passa a exibir no RH o PDF fechado, a situação de leitura do colaborador, a data/hora da ciência e o PDF assinado. O colaborador precisa abrir o relatório, confirmar que o conferiu e autenticar a assinatura com sua senha pessoal de ponto de seis dígitos. O PDF assinado contém um bloco de assinatura eletrônica com nome, usuário, data/hora, identificador SHA-256 derivado do registro e IP registrado na auditoria. Trata-se de assinatura eletrônica interna do Portal RH, não de certificado digital ICP-Brasil.


## V8.3 — Abono de horas por atestado
O RH passa a informar, em cada atestado recebido, a quantidade exata de horas e minutos a serem abonados. O abono fica vinculado ao atestado e ao colaborador, aparece para o colaborador, entra no fechamento mensal e é exibido no PDF de ponto/banco de horas. As horas abonadas justificam a jornada prevista, mas não geram crédito de banco de horas. Em atestados com vários dias, o total informado é distribuído cronologicamente pelos dias úteis cobertos, limitado à jornada diária prevista.


## V8.4 — Plantões executados e intervalo individual
O perfil individual do colaborador passa a permitir a configuração de início e fim do intervalo de jornada. Esse período é descontado da jornada prevista nos cálculos mensais. O RH também pode registrar Plantão executado em sábado ou domingo, com duração padrão de 14h. O plantão gera crédito imediato no banco de horas, possui histórico próprio e entra no dashboard, no extrato do banco e no PDF mensal com a descrição Plantão executado. Registros duplicados para o mesmo colaborador/data são bloqueados e a remoção exige justificativa, revertendo automaticamente o crédito.


## V8.5 — Hardening de segurança
A V8.5 reforça autenticação, sessão, CSRF, proteção contra brute force, PIN de ponto, headers HTTP, cache de documentos sensíveis, política de senha, validação real de PDFs/imagens e tratamento seguro de erros. Consulte `SECURITY.md` antes de publicar em produção.


## V8.5.1 — Correção de autenticação no Render
Corrige falso 403 no POST de login causado pela comparação absoluta de Origin atrás do proxy HTTPS do Render. A proteção CSRF permanece obrigatória e a validação adicional passa a comparar o host da origem com o host efetivo da requisição.
\n\n## V8.5.2 — Correção definitiva do 403 no login\nRemove a validação redundante de Origin que gerava falso bloqueio atrás do proxy reverso do Render. A proteção CSRF obrigatória permanece ativa em todos os POSTs, juntamente com cookies seguros, CSP, HSTS, proteção contra brute force e demais controles da V8.5.\n

## V8.6 — Central de Segurança do RH
Cria uma área exclusiva do administrador para monitorar autenticações, logins recusados, bloqueios, tentativas de PIN, acessos a holerites/atestados/documentos, redefinições de credenciais, assinaturas eletrônicas e ações críticas de auditoria. Os eventos de segurança passam a ser persistidos no PostgreSQL, inclusive quando não existe usuário autenticado.


## V8.7 — Duas vias do fechamento e reabertura de competência
Após a assinatura eletrônica do colaborador, o RH passa a validar o fechamento final. Somente após essa validação a via definitiva fica arquivada permanentemente na área "Meus fechamentos" do colaborador, enquanto o RH mantém acesso à mesma versão final. O PDF assinado passa a registrar também a validação final do RH. O RH pode reabrir uma competência fechada mediante justificativa obrigatória; ao reabrir, ciência e validação anteriores são invalidadas e será exigido novo ciclo de fechamento e assinatura.
