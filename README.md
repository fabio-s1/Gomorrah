# Gomorrah

Aplicação web de controle pessoal de gastos e receitas, feita para rodar **na sua própria máquina
ou servidor**. Sem conta em nuvem, sem anúncios: os dados ficam num arquivo SQLite que só você controla.
Funciona no navegador do PC e pode ser instalada no celular como app (PWA).

## Funcionalidades

- **Painel mensal:** saldo, receitas, despesas, uso do orçamento, insights em linguagem simples, gastos por categoria e tendência de 6 meses
- **Lançamentos:** cadastro, edição e exclusão, com busca e filtros por tipo e categoria
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

O app precisa de **HTTPS** para ser instalável (o Chrome só oferece "Instalar app" em HTTPS). Opções:

- **Tailscale (privado):** instale no PC/servidor e no celular e rode `tailscale serve --bg 5000`. Você recebe um endereço `https://….ts.net` acessível só pelos seus aparelhos.
- **Cloudflare Tunnel (domínio próprio):** expõe `https://gomorrah.seudominio.com` sem abrir portas. Use junto com Cloudflare Access e a senha do app.
- **Wi-Fi local:** `flask --app app run --host 0.0.0.0` e abra `http://IP-DO-PC:5000`. Funciona como site, sem instalação como app. Defina `GOMORRAH_PASSWORD`.

Servidor 24/7 (Raspberry Pi, VPS): use Gunicorn em vez do servidor de desenvolvimento:
`pip install gunicorn && gunicorn --preload -w 2 -b 127.0.0.1:8000 app:app`.
Nunca use `--debug` fora do seu computador de desenvolvimento.

## Carteiras e patrimônio

Cada **carteira** é um dinheiro separado: conta bancária, corretora, benefício (VR/VA), dinheiro vivo ou outro.

- **Saldo da carteira** = saldo inicial + receitas − despesas + transferências recebidas − transferências enviadas.
- **Transferências** movem dinheiro entre carteiras (ex.: conta → corretora) e **não contam como receita nem despesa**, então não distorcem o resultado do mês.
- **Patrimônio total** (`/carteiras`) soma os saldos ao fim do mês escolhido, mostra a distribuição, o saldo por tipo e a evolução de 6 meses.
- O **Painel** pode ser filtrado por carteira (chips no topo). Orçamentos são globais: no filtro por carteira, os gastos aparecem "sem orçamento".
- **Investimentos:** registre aportes como transferência e rendimentos como receita na carteira da corretora. O saldo **não acompanha a cotação** dos ativos.

**Atualizando de uma versão sem carteiras:** ao iniciar, `migrate_db()` (em `app.py`) adiciona a coluna `wallet_id`, cria a "Carteira principal" e vincula a ela todos os lançamentos antigos. Faça backup de `instance/gomorrah.db` antes. Esse é o padrão a seguir quando precisar adicionar colunas a um banco já existente.

## Estrutura do projeto

```
Gomorrah/
├── app.py              # app Flask: rotas, login, CSRF, PWA, CSV, consultas
├── models.py           # tabelas: Category, Wallet, Transaction, Transfer, Budget
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

## Manutenção

**Backup:** copie `instance/gomorrah.db` ou use Ajustes → Exportar CSV. Restaurar: pare o app e substitua o arquivo.

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

Não há testes automatizados ainda; ao mexer no código, teste manualmente as telas e o CSV.

## Privacidade e GitHub

O repositório deve conter **somente código**. Seus dados ficam em `instance/` e em qualquer `.csv`/`.db`,
todos ignorados pelo `.gitignore`. Antes de cada commit, rode `git status` e confira que nenhum desses arquivos aparece.
Se um banco ou chave for versionado por engano, apagar o arquivo depois **não basta** (ele continua no histórico):
reescreva o histórico antes de publicar e, se já publicou, troque a senha e apague `instance/secret.key`.
