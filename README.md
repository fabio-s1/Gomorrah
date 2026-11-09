# Gomorrah

Aplicação web de controle pessoal de gastos e receitas, feita para rodar **na sua própria máquina
ou servidor**. Sem conta em nuvem, sem anúncios: os dados ficam num arquivo SQLite que só você controla.
Funciona no navegador do PC e pode ser instalada no celular como app (PWA).

## Funcionalidades

- **Painel mensal:** saldo, receitas, despesas, uso do orçamento, insights em linguagem simples, gastos por categoria e tendência de 6 meses
- **Lançamentos:** cadastro, edição e exclusão, com busca e filtros por tipo e categoria
- **Metas de economia:** objetivo com valor e prazo ligado a uma carteira, com progresso e quanto guardar por mês
- **Lançamentos recorrentes:** aluguel, salário, assinaturas: o lançamento é criado sozinho no dia do vencimento
- **Orçamento por categoria e mês:** barra verde/amarela (a partir de 80%)/vermelha (acima de 100%) e cópia do mês anterior
- **Categorias** personalizáveis
- **Carteiras:** várias "contas" separadas (banco, corretora, VR/VA, dinheiro), transferências entre elas, painel de patrimônio com distribuição, evolução e filtro por carteira em todo o painel
- **CSV:** exportar e importar lançamentos e orçamentos, com relatório de erros por linha
- **Segurança:** login por senha opcional e proteção CSRF em todos os formulários
- **Mobile-first:** barra de abas, botão "+" e interface adaptada; instalável como app

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem e framework | Python 3.10+ e Flask |
| Banco de dados | SQLite via Flask-SQLAlchemy |
| Interface | Jinja2 + HTML/CSS puro (sem Node, sem build) |
| App no celular | PWA: `manifest.webmanifest` + service worker |

## Início rápido

**Windows (PowerShell)**

```powershell
git clone <url-do-repositorio> Gomorrah
cd Gomorrah
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app run
```

**Linux / macOS**

```bash
git clone <url-do-repositorio> Gomorrah
cd Gomorrah
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run
```

Abra http://127.0.0.1:5000. Na primeira execução o banco e as categorias iniciais são criados sozinhos.

- Se o PowerShell bloquear a ativação do ambiente: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Se o comando `flask` não for encontrado: use `python -m flask --app app run`.

### Variáveis de ambiente

| Variável | Para que serve |
|---|---|
| `GOMORRAH_PASSWORD` | Ativa a tela de login. **Obrigatória** se o app for acessível por outros aparelhos. Sem ela, não há login. |
| `SECRET_KEY` | Chave que assina a sessão. Opcional: se ausente, uma chave aleatória é criada em `instance/secret.key`. |

PowerShell: `$env:GOMORRAH_PASSWORD="sua-senha"` · Linux/macOS: `export GOMORRAH_PASSWORD="sua-senha"`
(vale só para o terminal atual).

## Usar no celular e fora de casa

O app precisa de **HTTPS** para ser instalável (o Chrome só oferece "Instalar app" em HTTPS; no iPhone use Compartilhar → Adicionar à Tela de Início). Opções:

- **Tailscale (privado, recomendado):** só os seus aparelhos acessam e não há portas abertas na internet. Passo a passo em [Implantação em servidor](#implantação-em-servidor-raspberry-pi--debian). Em um PC de desenvolvimento, rode `tailscale serve --bg 5000` e abra o endereço `https://….ts.net` mostrado.
- **Cloudflare Tunnel (domínio próprio):** expõe `https://gomorrah.seudominio.com` sem abrir portas. Use junto com Cloudflare Access e a senha do app.
- **Wi-Fi local:** `flask --app app run --host 0.0.0.0` e abra `http://IP-DO-PC:5000`. Funciona como site, sem instalação como app. **Defina `GOMORRAH_PASSWORD`.**

Nunca use `--debug` fora do seu computador de desenvolvimento.

## Carteiras e patrimônio

Cada **carteira** é um dinheiro separado: conta bancária, corretora, benefício (VR/VA), dinheiro vivo ou outro.

- **Saldo da carteira** = saldo inicial + receitas − despesas + transferências recebidas − transferências enviadas.
- **Transferências** movem dinheiro entre carteiras (ex.: conta → corretora) e **não contam como receita nem despesa**, então não distorcem o resultado do mês.
- **Patrimônio total** (`/carteiras`) soma os saldos ao fim do mês escolhido, mostra a distribuição, o saldo por tipo e a evolução de 6 meses.
- O **Painel** pode ser filtrado por carteira (chips no topo). Orçamentos são globais: no filtro por carteira, os gastos aparecem "sem orçamento".
- **Investimentos:** registre aportes como transferência e rendimentos como receita na carteira da corretora. O saldo **não acompanha a cotação** dos ativos.

**Atualizando de uma versão sem carteiras:** ao iniciar, `migrate_db()` (em `app.py`) adiciona a coluna `wallet_id`, cria a "Carteira principal" e vincula a ela todos os lançamentos antigos. Faça backup de `instance/gomorrah.db` antes. Esse é o padrão a seguir quando precisar adicionar colunas a um banco já existente.

## Planejamento: metas e recorrentes

A aba **Planejar** reúne Orçamentos, Metas e Recorrentes.

- **Recorrentes:** cadastre descrição, valor, carteira, categoria e dia do mês. Na primeira vez que o app é aberto a partir do vencimento, `generate_recurring()` (em `app.py`) cria o lançamento real e agenda o próximo mês. Dia 31 vira o último dia dos meses curtos. Excluir um recorrente mantém os lançamentos já criados; pausar e retomar não gera o que venceu durante a pausa.
- **Metas:** o progresso é o **saldo da carteira vinculada**. Crie uma carteira por objetivo (ex.: "Reserva de emergência") e use "Guardar dinheiro" para transferir até ela. Com prazo, o app mostra quanto guardar por mês.
- **CSV:** a exportação não inclui recorrentes nem metas. Para migrar tudo, copie `instance/gomorrah.db`.

## Estrutura do projeto

```
Gomorrah/
├── app.py              # app Flask: rotas, login, CSRF, PWA, CSV, consultas
├── models.py           # tabelas: Category, Wallet, Transaction, Transfer, Budget, Recurring, Goal
├── helpers.py          # funções puras: moeda (brl), meses, leitura de valores
├── requirements.txt    # dependências Python
├── README.md
├── .gitignore
├── static/
│   ├── style.css       # todo o visual (variáveis de cor em :root)
│   ├── sw.js           # service worker (PWA)
│   └── icons/          # ícones do app (192, 512 e apple-touch)
├── templates/          # HTML (Jinja2)
│   ├── base.html       # layout: cabeçalho, abas, menu, botão "+"
│   ├── _macros.html    # pedaços reutilizáveis: navegação de mês, lista de lançamentos
│   ├── index.html      # painel
│   ├── wallets.html, wallet_form.html, transfer_form.html   # carteiras e patrimônio
│   ├── goals.html, goal_form.html, recurrings.html, recurring_form.html   # planejamento
│   ├── transactions.html, form.html, budgets.html, settings.html
│   └── login.html, offline.html
└── instance/           # CRIADA AO RODAR. Dados privados, nunca versionada
    ├── gomorrah.db     # suas finanças (SQLite)
    └── secret.key      # chave de sessão
```

## Como funciona

1. O navegador pede uma URL, por exemplo `/?mes=2026-10`.
2. `guard()` (em `app.py`) roda antes de toda rota: valida o token CSRF nos POST e exige login se `GOMORRAH_PASSWORD` estiver definida.
3. A rota consulta o banco com SQLAlchemy e monta os dados (totais, categorias, tendência, insights).
4. O Jinja2 preenche um template e devolve HTML pronto. Não há API separada nem JavaScript de aplicação.
5. O service worker guarda só arquivos estáticos para abrir mais rápido. **Dados financeiros nunca vão para o cache.**

Decisões importantes:

- **Dinheiro em centavos inteiros** (`amount_cents`): evita erros de `float` (0.1 + 0.2 ≠ 0.3). A formatação `R$ 1.234,56` só acontece na exibição (`brl`).
- **Mês como texto `AAAA-MM`** nos orçamentos e na URL (`?mes=`).
- **Excluir é sempre POST + CSRF**, nunca um link simples.
- **O service worker fica em `/sw.js`** (raiz) para controlar o site inteiro.

### Rotas

| Rota | Função |
|---|---|
| `/` | Painel do mês |
| `/lancamentos` · `/lancamentos/novo` · `/lancamentos/<id>/editar` · `/lancamentos/<id>/excluir` | Lista, cria, edita, exclui |
| `/orcamentos` · `/orcamentos/copiar` | Define e copia orçamentos do mês |
| `/carteiras` · `/carteiras/nova` · `/carteiras/<id>/editar` · `/carteiras/<id>/excluir` | Patrimônio e gestão das carteiras |
| `/transferencias/nova` · `/transferencias/<id>/excluir` | Transferências entre carteiras |
| `/metas` · `/metas/nova` · `/metas/<id>/editar` · `/metas/<id>/excluir` | Metas de economia |
| `/recorrentes` · `/recorrentes/novo` · `/recorrentes/<id>/editar` · `/recorrentes/<id>/alternar` · `/recorrentes/<id>/excluir` | Lançamentos recorrentes |
| `/ajustes` · `/categorias` · `/categorias/<id>/excluir` | Categorias, dados e conta |
| `/dados/exportar.csv` · `/dados/importar` | Backup e migração em CSV |
| `/entrar` · `/sair` | Login e logout |
| `/manifest.webmanifest` · `/sw.js` · `/offline` | PWA |

### Banco de dados

| Tabela | Campos |
|---|---|
| `category` | `id`, `name` (único) |
| `wallet` | `id`, `name` (único), `kind`, `opening_cents` (saldo inicial) |
| `transaction` | `id`, `description`, `amount_cents`, `kind` (`receita`/`despesa`), `date`, `category_id`, `wallet_id` |
| `transfer` | `id`, `description`, `amount_cents`, `date`, `from_wallet_id`, `to_wallet_id` |
| `recurring` | `id`, `description`, `amount_cents`, `kind`, `day`, `next_due`, `end_date`, `active`, `category_id`, `wallet_id` |
| `goal` | `id`, `name`, `target_cents`, `deadline`, `wallet_id` |
| `budget` | `id`, `category_id`, `month` (`AAAA-MM`), `amount_cents` (único por categoria+mês) |

### Formato do CSV

Cabeçalho: `tipo,data,valor,categoria,descricao,carteira,destino`. Os valores aceitos em `tipo`:

| tipo | Campos usados |
|---|---|
| `carteira` | `carteira` = nome, `valor` = saldo inicial, `descricao` = tipo (`conta`, `corretora`, `beneficio`, `dinheiro`, `outro`) |
| `receita` / `despesa` | `data`, `valor`, `categoria`, `descricao`, `carteira` (vazio = primeira carteira) |
| `transferencia` | `data`, `valor`, `descricao`, `carteira` = origem, `destino` |
| `orcamento` | `data` (só o mês importa), `valor`, `categoria` |

`data` em `AAAA-MM-DD`; `valor` aceita `49.90`, `49,90` ou `1.234,56`. Carteiras citadas que não existem são criadas. CSVs antigos (sem as colunas `carteira` e `destino`) continuam funcionando.

## Implantação em servidor (Raspberry Pi / Debian)

Para deixar o Gomorrah no ar 24 horas em casa. Testado no Debian 12 (Raspberry Pi OS). Troque `USUARIO` e `NOME-DO-SERVIDOR` pelos seus.

### 1. Preparar o sistema e instalar

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip sqlite3
sudo timedatectl set-timezone America/Sao_Paulo
git clone <url-do-repositorio> ~/gomorrah
cd ~/gomorrah
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt gunicorn
```

Ajuste o fuso ao seu: os lançamentos recorrentes são criados pela **data do servidor**, e um fuso errado muda o dia do vencimento. Não rode o app antes de copiar o seu banco (se estiver migrando de outra máquina), porque ele criaria um banco vazio.

### 2. Criar o serviço (sobe sozinho ao ligar)

```bash
sudo tee /etc/gomorrah.env > /dev/null << 'EOF'
GOMORRAH_PASSWORD=troque-por-uma-senha-forte
EOF
sudo chmod 600 /etc/gomorrah.env

sudo tee /etc/systemd/system/gomorrah.service > /dev/null << EOF
[Unit]
Description=Gomorrah (controle financeiro)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/gomorrah
EnvironmentFile=/etc/gomorrah.env
ExecStart=$HOME/gomorrah/.venv/bin/gunicorn --preload -w 2 -b 127.0.0.1:8000 app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now gomorrah
systemctl status gomorrah --no-pager
```

A senha fica num arquivo que só o root lê. No segundo bloco o `EOF` está **sem aspas** de propósito, para o terminal preencher `$USER` e `$HOME`. O endereço `127.0.0.1:8000` deixa o app acessível só pelo próprio servidor (use com o Tailscale). Para testar pela rede local, troque temporariamente por `0.0.0.0:8000`, com a senha definida, e rode `sudo systemctl daemon-reload && sudo systemctl restart gomorrah`.

| Quero... | Comando |
|---|---|
| Parar / iniciar / reiniciar | `sudo systemctl stop gomorrah` · `start` · `restart` |
| Ver se está no ar | `systemctl status gomorrah --no-pager` |
| Ver erros recentes | `sudo journalctl -u gomorrah -n 50 --no-pager` |
| Acompanhar o log ao vivo | `sudo journalctl -u gomorrah -f` |

### 3. Acesso privado com Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve --bg 8000
sudo tailscale serve status
```

1. No painel do Tailscale (login.tailscale.com/admin/dns), ligue o **MagicDNS** e os **HTTPS Certificates**.
2. Em **Machines**, use **Disable key expiry** no servidor, ou ele sai da rede quando a chave expirar.
3. Abra o endereço `https://NOME.SUA-REDE.ts.net` mostrado pelo `status` (a primeira visita pode demorar alguns segundos para emitir o certificado) e instale o app pelo navegador do celular.
4. Para desfazer: `sudo tailscale serve --https=443 off`.

O `--bg` mantém a publicação ativa depois de fechar o terminal e após reiniciar o servidor.

### 4. Atualizar o código no servidor

Edite e teste no seu computador, envie ao GitHub e, no servidor:

```bash
~/bin/gomorrah-backup.sh                      # veja "Backup e restauração"
sudo systemctl stop gomorrah
cd ~/gomorrah && git pull
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl start gomorrah
sudo journalctl -u gomorrah -n 20 --no-pager
```

O Gunicorn mantém o código na memória, então mudanças só valem depois de reiniciar o serviço. Os dados em `instance/` não são tocados pelo `git pull`.

## Backup e restauração

O único arquivo essencial é **`instance/gomorrah.db`** (lançamentos, carteiras, categorias, orçamentos, metas e recorrentes). O código está no GitHub e o `.venv` se recria. A senha fica em `/etc/gomorrah.env`: guarde-a no seu gerenciador de senhas, não junto com o banco. `instance/secret.key` é dispensável (sem ele, só é preciso entrar de novo).

Não copie o arquivo com o app em uso: use o `.backup` do SQLite, que gera uma cópia consistente. Script de backup no servidor (`~/bin/gomorrah-backup.sh`):

```bash
mkdir -p ~/bin ~/backups && chmod 700 ~/backups
tee ~/bin/gomorrah-backup.sh > /dev/null << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
DB="$HOME/gomorrah/instance/gomorrah.db"
DEST="$HOME/backups"
OUT="$DEST/gomorrah-$(date +%F_%H%M).db"

sqlite3 "$DB" ".backup '$OUT'"
if [ "$(sqlite3 "$OUT" 'PRAGMA integrity_check;')" != "ok" ]; then
  echo "Backup corrompido, descartado: $OUT" >&2
  rm -f "$OUT"
  exit 1
fi
chmod 600 "$OUT"

# mantém só os 30 mais recentes
ls -1t "$DEST"/gomorrah-*.db | tail -n +31 | xargs -r rm --
echo "Backup criado: $OUT"
EOF
chmod 700 ~/bin/gomorrah-backup.sh
```

**Semanal e automático** (domingo, 3h):

```bash
(crontab -l 2>/dev/null; echo '0 3 * * 0 $HOME/bin/gomorrah-backup.sh >> $HOME/backups/backup.log 2>&1') | crontab -
```

**Copiar para o seu computador** (um backup que mora só no cartão SD não protege contra falha do cartão). Passo a passo, no PowerShell:

```powershell
ssh USUARIO@NOME-DO-SERVIDOR "~/bin/gomorrah-backup.sh"
scp USUARIO@NOME-DO-SERVIDOR:~/backups/gomorrah-AAAA-MM-DD_HHMM.db D:\Backups\Gomorrah\
Get-FileHash D:\Backups\Gomorrah\gomorrah-AAAA-MM-DD_HHMM.db -Algorithm SHA256
ssh USUARIO@NOME-DO-SERVIDOR "sha256sum ~/backups/gomorrah-AAAA-MM-DD_HHMM.db"
```

Os dois códigos SHA256 precisam ser iguais. Em Linux/macOS, use o mesmo `ssh`/`scp` e `sha256sum`.

<details>
<summary>Script PowerShell que faz tudo em um comando</summary>

```powershell
$Server = "USUARIO@NOME-DO-SERVIDOR"
$Dest   = "D:\Backups\Gomorrah"
New-Item -ItemType Directory -Force $Dest | Out-Null

$line   = ssh $Server "~/bin/gomorrah-backup.sh" | Select-Object -Last 1
$remote = $line -replace '^Backup criado: ', ''
$name   = Split-Path $remote -Leaf

scp "${Server}:$remote" $Dest
$local  = (Get-FileHash "$Dest\$name" -Algorithm SHA256).Hash
$server = (ssh $Server "sha256sum '$remote'").Split(' ')[0]

if ($local -ieq $server) { Write-Host "OK: $name copiado e conferido" -ForegroundColor Green }
else { Write-Host "ERRO: o arquivo copiado difere do original" -ForegroundColor Red }
```

</details>

**Restaurar** (com o app parado):

```bash
sudo systemctl stop gomorrah
mv ~/gomorrah/instance/gomorrah.db ~/gomorrah/instance/gomorrah.db.antigo
```

```powershell
scp D:\Backups\Gomorrah\gomorrah-AAAA-MM-DD_HHMM.db USUARIO@NOME-DO-SERVIDOR:~/gomorrah/instance/gomorrah.db
```

```bash
chmod 600 ~/gomorrah/instance/gomorrah.db
sudo systemctl start gomorrah
```

Rotina sugerida: cópia semanal automática no servidor, cópia para o PC a cada 15 dias e uma cópia mensal em mídia externa. Os arquivos contêm todas as suas finanças: guarde em disco criptografado ou em um `.7z` com senha, nunca em nuvem sem criptografia nem no GitHub. **Teste a restauração ao menos uma vez.**

## Manutenção

**Backup:** veja [Backup e restauração](#backup-e-restauração). O CSV (Ajustes → Exportar CSV) é só uma camada extra: não inclui metas nem recorrentes.

**Adicionar um campo (ex.: "observação" em lançamentos):**
1. Declare a coluna em `models.py`.
2. **Atenção:** `db.create_all()` só cria tabelas que faltam; ele **não altera** tabelas existentes. Num banco que já tem dados, rode `ALTER TABLE` no SQLite ou adote o Flask-Migrate. Para testes sem dados importantes, exporte o CSV e apague `instance/gomorrah.db`.
3. Ajuste `save()` em `app.py`, `form.html`, a macro `tx_list` e a exportação/importação de CSV.

**Adicionar uma página:** crie a rota em `app.py`, um template que estenda `base.html` e inclua a página na lista `nav` do `base.html`.

**Mudar o visual:** as cores estão nas variáveis de `:root` em `static/style.css`.

**Categorias iniciais:** `DEFAULT_CATEGORIES` em `app.py` só vale para banco novo e vazio.

**PWA:** ao alterar arquivos em `static/`, aumente o `V` em `static/sw.js` (ex.: `gomorrah-v2`) para forçar a atualização do cache nos aparelhos.

**Atualizar dependências:** `pip install -U -r requirements.txt`. Se uma versão nova do SQLAlchemy quebrar o app, fixe a anterior em `requirements.txt` (ex.: `sqlalchemy<2.1`).

**Problemas comuns**

| Sintoma | Solução |
|---|---|
| `flask` não reconhecido | `python -m flask --app app run` |
| Ativação do ambiente bloqueada (Windows) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Porta 5000 ocupada | `flask --app app run --port 5001` |
| Não aparece "Instalar app" | Use o endereço HTTPS, recarregue a página uma vez |
| "Sem conexão" no celular | Servidor parado ou VPN/rede desconectada |
| Recorrentes criados no dia errado | Confira o fuso do servidor com `timedatectl` |
| 502 / Bad Gateway pelo Tailscale | O serviço caiu: `sudo systemctl restart gomorrah` e `journalctl -u gomorrah` |

Não há testes automatizados ainda; ao mexer no código, teste manualmente as telas e o CSV.

## Privacidade e GitHub

O repositório deve conter **somente código**. Seus dados ficam em `instance/` e em qualquer `.csv`/`.db`,
todos ignorados pelo `.gitignore`. Antes de cada commit, rode `git status` e confira que nenhum desses arquivos aparece.
Se um banco ou chave for versionado por engano, apagar o arquivo depois **não basta** (ele continua no histórico):
reescreva o histórico antes de publicar e, se já publicou, troque a senha e apague `instance/secret.key`.

**Em produção:** use sempre `GOMORRAH_PASSWORD`, mantenha o Gunicorn escutando só em `127.0.0.1` atrás do Tailscale e não publique no GitHub o endereço da sua rede, IPs, usuários nem senhas. Os blocos deste README usam valores de exemplo (`USUARIO`, `NOME-DO-SERVIDOR`).
