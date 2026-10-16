# P16 — Backup automático que avisa, guarda cópia local e sobrevive à queda do Drive

**Status:** pronta para implementação — decisões fechadas em 16/10/2026 a partir da falha verificada em produção
**Prioridade:** P1

## Contexto

O backup automático do ERP está ligado, roda todo dia às 02:00 no horário de São Paulo, com retenção de 30 dias e destino no Google Drive. Na verificação de 16/10/2026, o estado real era:

- Último backup **bem-sucedido**: 14/10/2026, às 02:00.
- **Falha em 15/10/2026**, às 02:00, e repetindo diariamente desde então.
- Motivo registrado pelo ERP: o Google respondeu `400 Bad Request` na renovação da autorização de acesso ao Drive.
- O processo que agenda o backup está de pé e executando; o que quebrou foi a autorização, não o agendamento.

A causa mais provável, pela data: a conexão foi criada em 06/10/2026 e parou em 15/10/2026. Autorização de aplicativo em modo de **teste** no Google Cloud expira em cerca de 7 dias — exatamente o intervalo observado.

Três falhas do próprio ERP ficaram expostas junto com isso:

1. **Ninguém avisa.** O ERP grava a falha, mas não notifica, e a tela de Configurações mostra a data do último backup bem-sucedido ao lado de um status técnico, o que dá aparência de normalidade.
2. **O motivo real se perde.** Fica guardado apenas o `400 Bad Request`; o código devolvido pelo Google, que diria se a autorização expirou ou foi revogada, não é registrado.
3. **Existe um único destino.** Toda a proteção depende do Drive. Autorização expirada, internet fora ou Google indisponível deixam a loja sem nenhuma cópia nova do banco.

Além disso, há **1,3 GB** de backups locais gerados pelos deploys, sem rotina de limpeza.

O resultado é o pior tipo de falha: a proteção some em silêncio e o responsável só descobre por acaso.

## Objetivo

Fazer o backup falhar alto, e não em silêncio: avisar o responsável no mesmo dia, guardar sempre uma cópia local independente do Drive e mostrar com clareza quando o backup está atrasado.

## Decisões de negócio (fechadas)

1. **Falha de backup gera aviso ativo** para administrador e gerente: notificação no aplicativo e faixa de aviso dentro do ERP.
   - Por quê: o ERP sabia da falha e não contou nada; foi o que transformou uma falha de configuração em nove dias sem backup.
   - Alternativa descartada: corrigir só a conexão do Google e seguir — a próxima falha (senha trocada, Drive fora, internet caída) repetiria o silêncio.
2. **Existe estado de "backup atrasado"**, calculado pelo último sucesso e não pelo último registro: 36 horas no diário e 8 dias no semanal.
   - Por quê: não depende de o erro ter sido classificado corretamente nem de o job ter registrado a tentativa; se o último backup bom ficou velho, o ERP avisa.
   - Alternativa descartada: confiar apenas no último status gravado — foi justamente o que ficou ambíguo.
3. **Toda execução guarda uma cópia local antes de enviar** para o Drive, com a mesma retenção.
   - Por quê: um único destino não é backup; se o Drive estiver inacessível, ainda existe cópia no servidor.
   - Alternativa descartada: manter só o Drive, como hoje.
4. **O motivo devolvido pelo Google é guardado e mostrado em linguagem clara**, com botão de reconectar a conta.
   - Por quê: "400" não diz o que fazer; "a autorização expirou, reconecte a conta" diz.
   - Alternativa descartada: guardar apenas o código HTTP.
5. **A conta do Google Drive precisa ficar em modo de produção no Google Cloud**, fora do modo de teste, porque em teste a autorização expira em cerca de 7 dias.
   - Por quê: foi o que aconteceu; reconectar sem mudar isso derruba o backup de novo na semana seguinte.
   - Alternativa descartada: manter em modo de teste e reconectar toda semana.
6. **A conexão é validada no momento em que é configurada**, antes de o ERP marcar o backup como pronto.
   - Por quê: evita a situação atual, em que a tela diz que está tudo certo e a primeira falha aparece só no dia seguinte.
   - Alternativa descartada: confiar no retorno do navegador após a autorização.
7. **A tela mostra sempre três informações**: último sucesso, última tentativa e próximo previsto, com status em português.
   - Por quê: elimina a leitura errada de "14/10" parecendo o estado atual.
   - Alternativa descartada: manter data do último sucesso e status técnico lado a lado.
8. **Existe botão "fazer backup agora"**, com resultado na tela e registro no histórico.
   - Por quê: quando a pessoa reconecta ou suspeita de problema, precisa confirmar na hora, sem esperar as 02:00.
   - Alternativa descartada: esperar o próximo ciclo agendado.
9. **A retenção vale para todos os backups**: os do Drive e as cópias locais, incluindo as geradas pelos deploys.
   - Por quê: 1,3 GB acumulados sem regra, em um servidor que também hospeda a aplicação.
   - Alternativa descartada: limpar só o Drive e deixar o disco crescer sem limite.
10. **Restaurar continua sendo procedimento do operador**, não um botão na interface.
    - Por quê: restauração é operação de risco e feita fora do horário de uso; automatizar isso na tela é convite a acidente.
    - Alternativa descartada: botão de restaurar pela interface nesta entrega.

## Escopo

- Aviso de falha de backup por notificação e por faixa dentro do ERP, para administrador e gerente.
- Estado de "backup atrasado" calculado pelo último sucesso, para backup diário e semanal.
- Cópia local do banco em toda execução, com a mesma política de retenção do Drive.
- Registro do motivo real da falha (código devolvido pelo provedor) e exibição em português.
- Botão de reconectar a conta do Google Drive, disponível na tela de backup e no próprio aviso de falha.
- Validação do acesso no momento da configuração da conta.
- Botão "fazer backup agora", com resultado visível.
- Orientação na tela de que a conta no Google Cloud deve estar em modo de produção.
- Revisão da tela de backup: último sucesso, última tentativa, próximo previsto, status em português, motivo da falha e onde estão as cópias.
- Limpeza por retenção dos backups locais, incluindo os gerados pelos deploys.
- Datas exibidas em America/Sao_Paulo, sem deslocamento de dia.

## Critérios de aceite

1. Quando o backup agendado falha, a notificação é enviada a administrador e gerente e a faixa de aviso aparece no ERP no mesmo dia.
2. A tela de backup mostra a falha com o motivo em português e o botão de reconectar a conta.
3. O estado "backup atrasado" aparece quando o último sucesso passa de 36 horas no backup diário e de 8 dias no semanal, mesmo que o último registro tenha sido gravado como sucesso.
4. Toda execução bem-sucedida grava também uma cópia local no servidor, e a tela indica onde as cópias ficam.
5. Com o Drive inacessível ou a autorização inválida, o backup local do dia continua existindo e o ERP avisa.
6. O código de erro devolvido pelo provedor é guardado e exibido em texto claro, distinguindo autorização expirada de outros erros.
7. Depois de reconectar com autorização nova, a primeira execução bem-sucedida volta a marcar o backup como em dia e remove o aviso.
8. O botão "fazer backup agora" executa, informa o resultado na tela e registra a execução no histórico.
9. Ao configurar a conta, o ERP valida o acesso e só então marca o backup como pronto; falha na validação é mostrada na hora.
10. A retenção remove backups vencidos no Drive e nas cópias locais, e não remove nenhum arquivo dentro do prazo.
11. A tela nunca mostra a data do último sucesso sem indicar que houve falha depois dela.
12. Todas as datas aparecem no fuso America/Sao_Paulo, sem deslocar o dia.

## Fora de escopo

- Backups em outros provedores (OneDrive, S3 ou equivalente).
- Backup contínuo ou restauração ponto a ponto do banco.
- Restauração pela interface, que continua sendo procedimento manual do operador.
- Migração para conta de serviço do Google em vez de autorização de usuário; fica como alternativa caso a expiração volte a incomodar.
- Backup dos arquivos anexados às compras e notas: **hoje o backup cobre o banco, não os anexos**. É uma limitação conhecida, registrada para avaliação em spec própria.

## Dependências e riscos

- Depende do fluxo atual de autorização do Google Drive e do sistema de notificações do ERP.
- **Ação imediata e fora desta spec:** reconectar a conta do Google Drive no ERP e publicar a tela de consentimento no Google Cloud. Sem isso, o backup continua parado independentemente do que for implementado.
- Risco: a autorização voltar a expirar por permanecer em modo de teste. Mitigado pelo aviso de atraso e pela orientação fixa na tela.
- Risco: a notificação não chegar por permissão negada no aparelho. Mitigado pela faixa de aviso dentro do ERP e pelo estado de atraso, que não dependem de push.
- Risco: as cópias locais encherem o disco do servidor. Mitigado pela retenção obrigatória.
- Risco: o valor de retenção ficar curto para o uso real. Mitigado por manter a retenção configurável, como já é hoje.

## Referências de mercado

| Prática consolidada | Onde se vê | Decisão para o Parts ERP |
| --- | --- | --- |
| Regra 3-2-1: mais de uma cópia e mais de um destino | Prática consolidada de backup em TI | Adotado em forma mínima: cópia local além do Drive |
| Monitoramento de backup com alerta de falha e de atraso | Odoo, NetSuite e ferramentas de banco gerenciado | Adotado: aviso no mesmo dia e estado de atraso pelo último sucesso |
| Reconexão guiada quando a credencial do provedor expira | Google Workspace, Microsoft 365 | Adotado: motivo claro, botão de reconectar e validação na configuração |

## Faseamento

- **Primeira entrega:** aviso de falha e de atraso, motivo claro, botão de reconectar e cópia local do banco. É o bloco que garante que o responsável saiba e que exista cópia fora do Drive.
- **Segunda entrega:** botão "fazer backup agora", revisão completa da tela de backup e limpeza por retenção das cópias locais.
