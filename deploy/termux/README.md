# Implantação no Termux

Perfil leve para Android sem root: FastAPI e ARQ em um virtualenv, SQLite em modo WAL,
Redis apenas em loopback e Nginx na porta 8080.

## Instalação

Use o Termux do F-Droid ou GitHub e instale o Termux:Boot pela mesma fonte.

```bash
pkg update
pkg install git python nodejs-lts nginx redis clang make pkg-config openssl libffi python-cryptography tur-repo
git clone https://github.com/felgoes/parts-erp.git ~/parts-erp
cd ~/parts-erp
bash deploy/termux/install.sh
bash deploy/termux/start.sh
```

A senha inicial fica somente no aparelho, em `data/initial-admin-password`. Guarde-a e
apague esse arquivo. O `backend/.env` é criado com permissão `600` e recebe chaves aleatórias.

O ERP fica disponível na rede local em `http://IP_DO_CELULAR:8080`. Redis e FastAPI escutam
apenas em loopback. Para iniciar após reinicializações, abra o Termux:Boot uma vez e desative
a otimização de bateria para Termux e Termux:Boot.

## Operação

```bash
bash deploy/termux/start.sh
bash deploy/termux/stop.sh
bash deploy/termux/verify.sh
tail -f data/logs/api.log
```

Faça backup consistente com `sqlite3 data/parts-erp.db ".backup 'backup.db'"` e inclua também
`data/documents`. O script `deploy/update-s9.sh`, executado no computador, cria um backup antes
de migrar o banco.
