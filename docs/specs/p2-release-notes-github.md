# P2 — Notas de atualização vinculadas às versões no GitHub

**Status:** concluído
**Prioridade:** P2

## Objetivo

Manter notas de atualização breves, datadas e úteis para usuários, acessíveis pelo README e ligadas ao código publicado no GitHub.

## Regras

- Após cada deploy confirmado em produção, registrar as novidades visíveis ao usuário e a data efetiva do deploy.
- Vincular cada nota ao commit exato implantado no GitHub. Para o ERP web, que ainda não possui tags semânticas, o SHA do commit é a referência imutável da versão publicada.
- Na recuperação retroativa, usar os commits disponíveis e identificá-los como histórico por data de commit; não inferir datas de deploy ausentes.
- Manter o arquivo RELEASE_NOTES.md conciso e em português, priorizando mudanças de produto. O README.md deve oferecer acesso direto às notas.
- Não divulgar detalhes internos de segurança, infraestrutura ou configuração.

## Critérios de aceite

1. O README possui link visível para RELEASE_NOTES.md.
2. As notas cobrem o histórico de funcionalidades recuperável dos commits existentes e indicam seus commits do GitHub.
3. Datas de deploy confirmadas são diferenciadas de datas de commit usadas no histórico retroativo.
4. Cada novo deploy em PRD recebe uma nota curta ligada ao commit implantado.
5. O texto está atualizado, em português natural e sem avisos antigos que contradigam funcionalidades atuais.
