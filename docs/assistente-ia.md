# Assistente de IA

O assistente é exclusivo do perfil `admin`. Ele abre pelo botão flutuante "Assistente" em qualquer
tela autenticada e usa a configuração compartilhada de Integrações; cada administrador vê apenas o
próprio histórico.

## Configuração

Em **Configurações → Integrações → Assistente de IA**, escolha o provedor e o modelo, informe a
chave de API e defina o limite mensal em dólar. Provedores disponíveis:

- DeepSeek (`deepseek-chat`, `deepseek-reasoner`)
- OpenAI (`gpt-4.1-mini`, `gpt-4.1`)
- Google Gemini (`gemini-2.5-flash`, `gemini-2.5-pro`)
- Anthropic Claude (`claude-sonnet-4-5`, `claude-haiku-4-5`)

O botão "Testar conexão" confirma se a chave e o modelo respondem. A chave fica cifrada no servidor
e nunca volta completa para a tela. Trocar de provedor exige substituir ou remover a chave.

O limite é compartilhado entre administradores. O painel mostra o consumo estimado, o percentual e a
data de reinício; a partir de 80% aparece um aviso e, ao atingir o limite, novas solicitações são
bloqueadas até o próximo mês ou até o limite ser aumentado. Os preços são uma referência para
orçamento e podem não coincidir com a fatura do provedor. Se o modelo não tiver preço confiável, o
chat bloqueia em vez de mostrar custo zero.

## O que o assistente faz

- consulta produtos, saldos, compras e vendas pelo ERP;
- investiga a situação fiscal de uma venda usando somente estados, documentos e logs locais,
  distinguindo fatura interna de nota fiscal;
- prepara a criação de produto, a criação de compra e o ajuste de estoque.

As três escritas nunca acontecem direto pela resposta do modelo. O assistente mostra uma prévia com
os dados e as consequências e aguarda a confirmação do administrador na tela. A confirmação é
vinculada àquela prévia, revalida o estado do ERP e não duplica a operação se for repetida.

## Limites e privacidade

- O chat não executa comandos de shell, não altera configuração e não acessa o banco de forma livre.
- A investigação fiscal não consulta o marketplace nem outros sistemas externos.
- Dados enviados ao provedor são limitados ao necessário para a resposta; credenciais são filtradas.
- Excluir uma conversa não desfaz operações já realizadas nem apaga a auditoria da ação.
- O restante do ERP continua funcionando se o provedor estiver sem chave, indisponível ou acima do
  orçamento.

A validação com chaves reais dos quatro provedores é feita pelo operador no ambiente de produção;
os testes automatizados e o HML usam provedor simulado.
