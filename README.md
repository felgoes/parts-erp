# Parts ERP

[historical infra reference removed]

ERP web para uma loja de autopeças, com estoque, clientes, faturas de venda e sincronização de pedidos do Mercado Livre.

Veja as [notas de atualização](RELEASE_NOTES.md) e os commits correspondentes a cada versão publicada.

## Stack

- Angular 21 com componentes standalone e Signals
- FastAPI, SQLAlchemy 2, Alembic e PostgreSQL
- Redis + ARQ para processar notificações do Mercado Livre
- Docker Compose para desenvolvimento e implantação

## Recursos do MVP

- autenticação JWT e perfis `admin`, `manager` e `operator`;
- cadastro de produtos, preços, estoque mínimo e ajustes auditáveis;
- cadastro de clientes;
- faturas de venda em rascunho, confirmação e cancelamento;
- baixa e estorno de estoque transacionais e idempotentes;
- OAuth do Mercado Livre com tokens criptografados no banco;
- webhook assíncrono para importar pedidos sem duplicidade;
- vínculo de XML/DANFE emitidos pelo Faturador do Mercado Livre à venda.

## Executar localmente

1. Copie `.env.example` para `.env` e substitua todos os valores `change-me`.
2. Gere a chave Fernet indicada no próprio arquivo.
3. Execute `docker compose up --build -d`.
4. Crie o primeiro usuário:

```bash
docker compose exec backend python -m app.cli bootstrap-admin
```

O ERP estará em `http://localhost:4200` e a documentação da API em `http://localhost:8000/docs`.

## Validação visual local

Para alterações de interface, abra `http://localhost:4200` com a API local em execução e confira manualmente a tela no navegador, inclusive em largura mobile quando relevante. Use a conta de QA dedicada do banco local; neste checkout, as credenciais estão no arquivo ignorado `.env.qa.local`, sem reutilizar dados ou acesso de produção. A automação E2E não é requisito para ajustes visuais de rotina; use testes automatizados quando forem úteis para uma regressão lógica específica.

## Mercado Livre

Crie uma aplicação no painel de desenvolvedores, configure a URL de redirecionamento e preencha as variáveis `MERCADOLIVRE_*`. No ERP, abra **Integrações**, conecte a conta vendedora e cadastre `https://api.goesautoparts.com.br/api/v1/integrations/mercadolivre/webhook` como URL pública. Habilite os tópicos `orders_v2`, `shipments` e `invoices`; `shipments` é necessário para atualizar o rastreio à medida que o envio avança. O hostname público deve resolver no DNS e encaminhar ao backend do ERP.

O SKU do anúncio/variação precisa ser igual ao SKU do produto no ERP. Pedidos pagos geram uma fatura confirmada e baixam o estoque uma única vez. Notificações repetidas são seguras.

## Segurança

- Nenhum segredo é versionado; `.env` é ignorado.
- Tokens OAuth são criptografados com Fernet antes de persistir.
- Senhas usam Argon2 e os tokens de sessão têm expiração curta.
- O webhook não recebe nem aceita tokens e só enfileira recursos permitidos.
- Em produção, use HTTPS, senhas fortes, backup do PostgreSQL e um gerenciador de segredos.

Veja [docs/mercado-livre.md](docs/mercado-livre.md) para o fluxo e limitações da integração.
