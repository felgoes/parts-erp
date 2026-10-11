# Duas máquinas, uma pessoa (fluxo de alternância)

Você trabalha em dois PCs, mas nunca ao mesmo tempo: um de cada vez, sempre sozinho. O risco
real não é escrita simultânea — é **divergência**: a máquina A commita e não publica, a
máquina B começa de um `main` antigo, as duas publicam e nasce um merge com conflito em cima
das mesmas telas. Foi o que custou a maior parte de uma entrega inteira.

A regra que resolve isso em uma frase: **nenhuma máquina guarda commit sem publicar**.

## O ciclo em três comandos

```bash
./scripts/dev/sync.sh start     # começa aqui: busca o que a outra máquina publicou e recusa trabalho local pendente
... trabalhar: implementar, ./scripts/dev/checks.sh backend <filtro>, HML, commit ...
./scripts/dev/sync.sh finish    # encerra aqui: rebase se preciso, portão de checks e push
```

- `sync.sh status` mostra o retrato: o que está publicado, o que é local, o que divergiu e
  o que está sem commit.
- `start` faz `fetch`; se você está atrás, avança (`--ff-only`); se há commit local não
  publicado, **para e manda publicar antes de começar coisa nova**; se as duas máquinas têm
  commit, rebaseia com `--autostash` e mostra o que veio de lá.
- `finish` faz o mesmo alinhamento, exige a árvore sem pendências escondidas (commit antes),
  roda `./scripts/dev/checks.sh all` e publica. É o comando que você roda **antes de desligar
  ou trocar de PC**.

Tudo roda com `GIT_TERMINAL_PROMPT=0`: se a credencial falhar, o script avisa em segundos em
vez de ficar pendurado esperando senha (a ponte para o Git Credential Manager do Windows
resolve isso no WSL).

## Publicar cedo não atrapalha o deploy

O deploy continua exigindo `main == origin/main` e árvore limpa — ou seja, publicar cedo é
exatamente o que ele quer. Você pode (e deve) publicar várias vezes durante a tarefa; o
deploy é um passo separado, depois do portão de checks e da validação em HML.

## Quando vale uma branch por tarefa

| Situação | O que usar |
| --- | --- |
| Ajuste curto, um commit | `main` direto, publicando no fim |
| Tarefa com várias etapas ou risco de voltar atrás | branch `codex/<slug>`, rebase antes do push e merge na entrega |
| Vai pausar no meio da tarefa para trocar de máquina | publique o que existe (mesmo em branch de trabalho) — a outra máquina continua de onde parou |

Com branch, o `finish` publica a branch; o merge na `main` acontece quando a entrega estiver
validada, com `git merge --no-ff`.

## Documentação: um dono por arquivo

A fonte de verdade compartilhada é a fila do repositório privado de infraestrutura (`TASKS.md`,
com as specs de trabalho pendente). Este repositório do app é público e guarda o que já existe:
as specs entregues (`docs/specs/`) e as notas de produção (`RELEASE_NOTES.md`). Quem edita,
publica na hora — inclusive o agente de PO. Evite duas conversas editando o mesmo arquivo de
fila: foi assim que nasceu um conflito de "arquivo apagado de um lado, alterado do outro".

## Checklist ao trocar de máquina

1. Na máquina que você está deixando: `./scripts/dev/sync.sh finish` (ou no mínimo
   `sync.sh publish`). Nada de commit local guardado.
2. Na que você vai usar: `./scripts/dev/sync.sh start`. Se ele reclamar de commit não
   publicado, publique antes de seguir.
3. Se a máquina for nova: `docs/maquina-nova.md` no repositório privado de infraestrutura.
4. Ao terminar a tarefa: deploy pelo wrapper privado, smoke público e fechamento
   (`RELEASE_NOTES.md`, `Status:` da spec, `TASKS.md`).

## Se mesmo assim divergir

`sync.sh start` já rebaseia automaticamente com `--autostash`. Se o rebase parar em conflito,
resolva arquivo por arquivo preservando as duas entregas (as duas linhas são suas) e siga com
`git rebase --continue`; depois `./scripts/dev/checks.sh all` e `sync.sh publish`. Nunca use
`git reset --hard` nem descarte trabalho sem commit que não seja seu.
