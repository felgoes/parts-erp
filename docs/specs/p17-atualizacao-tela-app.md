# P17 — Atualizar a tela no app: puxar para atualizar e retomar a atualização automática

**Status:** entregue em 16/10/2026 (`7e50cd4`), validado no HML local: gesto, faixa de "sem atualização recente" e a conta da retomada estão cobertos por teste, e a faixa foi conferida na tela. A conferência em **aparelho Android real** (critério 9) continua pendente e depende do aparelho do operador — a mesma ressalva vale para o gesto dentro do WebView, que não é reproduzível no navegador de desenvolvimento.
**Prioridade:** P2

## Contexto

No desktop o ERP já se atualiza sozinho: toda alteração gravada publica um aviso, o navegador mantém uma conexão aberta com o servidor e a tela recarrega os dados em cerca de um segundo. Existem ainda duas redes de proteção: consulta automática a cada 20 segundos e recarga quando a janela ou a aba volta a ficar visível.

No aplicativo, isso não funciona igual. O app é uma casca que abre o próprio site do ERP, e quando o Android o coloca em segundo plano a conexão de atualização é congelada ou encerrada. Os eventos que deveriam recarregar a tela ao voltar (foco da janela e visibilidade da aba) não disparam de forma confiável dentro do app.

O resultado é o que o usuário relatou: arrastar a tela para baixo não atualiza, e a tela pode continuar mostrando número velho até ele trocar de página.

A dor é de confiança: em estoque, preço e venda, decidir em cima de dado desatualizado é pior do que não ter o dado. E o gesto de arrastar para atualizar é o reflexo natural de quem usa aplicativo no celular — quando não responde, a pessoa conclui que o sistema travou, não que a tela está velha.

## Objetivo

Garantir que a tela do app mostre o dado atual sempre que o usuário olhar para ela, com o gesto de puxar para atualizar funcionando e a atualização automática voltando a funcionar sozinha depois que o app fica em segundo plano.

## Decisões de negócio (fechadas)

1. **Puxar para baixo recarrega os dados da tela atual**, sem recarregar a página inteira.
   - Por quê: recarregar a página inteira perde o filtro aplicado, a posição da rolagem e qualquer coisa digitada em formulário aberto.
   - Alternativa descartada: recarregar o aplicativo do zero a cada gesto.
2. **Ao voltar para o app, a tela se atualiza sozinha.**
   - Por quê: é o momento em que o dado pode estar velho (o app ficou minutos ou horas em segundo plano) e é exatamente quando o usuário volta a olhar.
   - Alternativa descartada: depender do gesto manual para retomar.
3. **A conexão de atualização automática é reconectada ao retomar o app.**
   - Por quê: hoje ela pode ficar morta depois do segundo plano, e a atualização em tempo real some sem aviso.
   - Alternativa descartada: esperar o ciclo de 20 segundos como única saída.
4. **Nenhuma atualização automática pode apagar o que a pessoa está digitando.** Com formulário aberto e alteração não salva, a recarga automática espera ou pergunta.
   - Por quê: perder o preenchimento de uma compra ou de uma cotação por causa de uma recarga de fundo é pior do que ver um número velho por um instante.
   - Alternativa descartada: atualizar sempre, sem verificar o estado do formulário.
5. **Quando o app estiver sem contato com o servidor, ele avisa** numa faixa discreta, com a hora da última atualização e um botão de tentar agora, em vez de fingir que está tudo atualizado.
   - Por quê: silêncio com dado velho é o pior cenário; o usuário precisa saber quando o que está vendo pode não ser o atual.
   - Alternativa descartada: mostrar a tela normalmente sem nenhum sinal de conexão.
6. **O gesto de puxar para atualizar vale apenas no app.** No navegador do celular o próprio navegador já oferece o gesto, e no desktop a atualização é imediata.
   - Por quê: acrescentar o gesto no desktop não agrega e disputa com a rolagem.
   - Alternativa descartada: criar o gesto em todas as plataformas.
7. **A mudança entra sem reinstalar o aplicativo**, porque o app abre o site do ERP.
   - Por quê: evita publicar APK novo e pedir atualização de todos os aparelhos.
   - Alternativa descartada: tratar como mudança nativa que exige nova versão do aplicativo.

## Escopo

- Gesto de puxar para atualizar nas telas de lista e de painel do aplicativo.
- Indicador visual de "atualizando" durante o gesto, no padrão do próprio app.
- Atualização automática ao trazer o app de volta para a frente.
- Reconexão da atualização automática em tempo real ao retomar o app.
- Proteção contra perda de digitação quando houver formulário aberto com alteração não salva.
- Faixa de aviso de "sem atualização recente" com hora da última atualização e ação de tentar novamente.
- Funcionamento normal da rolagem: o gesto só dispara quando a tela está no topo.
- Teste em aparelho Android real, nas telas de compras, estoque, vendas e painel.

## Critérios de aceite

1. No app, puxar a tela para baixo no topo recarrega os dados da tela atual e mostra o indicador enquanto atualiza.
2. O gesto nunca recarrega a página inteira e não perde filtro aplicado, posição de rolagem ou conteúdo digitado.
3. Ao trazer o app do segundo plano para a frente, os dados da tela são atualizados sem ação do usuário.
4. Depois de o app ficar em segundo plano por mais de um minuto, uma alteração feita em outro aparelho aparece na tela em até 20 segundos, sem reabrir o aplicativo.
5. Com o app em primeiro plano, uma alteração feita em outro aparelho aparece em cerca de um segundo.
6. Com o servidor fora de alcance, aparece faixa discreta com a hora da última atualização e botão de tentar novamente; quando a conexão volta, a faixa desaparece sozinha.
7. Com formulário aberto e alteração não salva, a atualização automática não apaga nem sobrescreve o conteúdo digitado.
8. A rolagem normal da tela continua funcionando; o gesto só é capturado quando a tela está no topo.
9. O comportamento é verificado em aparelho Android real nas telas de compras, estoque, vendas e painel.
10. Datas e horas mostradas no aviso seguem o fuso America/Sao_Paulo, sem deslocamento de dia.

## Fora de escopo

- Operação sem internet, com fila de lançamentos para enviar depois; o app continua exigindo servidor.
- Notificações push, que têm spec própria.
- Alterações que exijam publicar nova versão do aplicativo.
- Revisão visual geral do app ou mudança de identidade.

## Dependências e riscos

- Depende do serviço de atualização em tempo real e do canal de avisos já existentes no ERP.
- Risco: alguns aparelhos Android não dispararem os eventos de visibilidade do WebView. Mitigado usando também o evento nativo de retomada do aplicativo e o ciclo de 20 segundos como rede de proteção.
- Risco: a atualização automática competir com digitação em formulário aberto. Mitigado pela decisão 4, que faz a recarga esperar.
- Risco: o gesto interferir na rolagem. Mitigado pela decisão de só capturar o gesto no topo da tela e pelo teste em aparelho real.

## Referências de mercado

| Prática consolidada | Onde se vê | Decisão para o Parts ERP |
| --- | --- | --- |
| Puxar para atualizar é gesto padrão de lista em aplicativo móvel | Aplicativos iOS e Android em geral | Adotado: gesto nas telas de lista e painel |
| Recarregar dados ao trazer o app para a frente | Salesforce Mobile, Odoo Mobile | Adotado: atualização automática na retomada |
| Estado visível de "sem conexão" com hora da última atualização | Microsoft Dynamics 365, Salesforce Mobile | Adotado: faixa discreta com hora e ação de tentar novamente |

## Faseamento

Entrega única: gesto, retomada, reconexão, proteção de digitação e aviso de conexão formam um comportamento só. Entregar o gesto sem a proteção de digitação ou sem a retomada deixaria metade do problema de pé.
