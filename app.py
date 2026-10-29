import csv
import io
import os
import secrets
import time
from datetime import date
from decimal import InvalidOperation

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for, Response)
from sqlalchemy import func, text

from helpers import MONTHS, WALLET_KINDS, brl, dec, month_bounds, parse_amount
from models import Budget, Category, Transaction, Transfer, Wallet, db

DEFAULT_CATEGORIES = ["Moradia", "Mercado", "Transporte", "Lazer",
                      "Saúde", "Educação", "Salário", "Outros"]
PUBLIC = {"login", "static", "manifest", "service_worker", "offline"}


class Bad(Exception):
    """Erro de validação com mensagem amigável."""


def ym(d):
    return d.strftime("%Y-%m")


def last_months(start, n=6):
    months = [start]
    for _ in range(n - 1):
        months.insert(0, month_bounds(ym(months[0]))[2])
    return months


def wallet_arg():
    """Lê ?carteira=<id> da URL; None se ausente ou inexistente."""
    raw = request.args.get("carteira", "")
    return int(raw) if raw.isdigit() and db.session.get(Wallet, int(raw)) else None


def totals(a, b, wid=None):
    q = (db.session.query(Transaction.kind, func.sum(Transaction.amount_cents))
         .filter(Transaction.date >= a, Transaction.date < b))
    if wid:
        q = q.filter(Transaction.wallet_id == wid)
    rows = dict(q.group_by(Transaction.kind).all())
    return rows.get("receita", 0), rows.get("despesa", 0)


def category_rows(start, nxt, wid=None):
    """Gasto x orçamento de cada categoria no mês (orçamentos são globais)."""
    q = (db.session.query(Transaction.category_id, func.sum(Transaction.amount_cents))
         .filter(Transaction.kind == "despesa", Transaction.date >= start, Transaction.date < nxt))
    if wid:
        q = q.filter(Transaction.wallet_id == wid)
    spent = dict(q.group_by(Transaction.category_id).all())
    budgets = {} if wid else {b.category_id: b.amount_cents
                              for b in Budget.query.filter_by(month=ym(start))}
    rows = []
    for c in Category.query.order_by(Category.name):
        s, b = spent.get(c.id, 0), budgets.get(c.id, 0)
        rows.append({"id": c.id, "name": c.name, "spent": s, "budget": b,
                     "pct": round(s * 100 / b) if b else 0})
    if spent.get(None):
        rows.append({"id": None, "name": "Sem categoria", "spent": spent[None], "budget": 0, "pct": 0})
    return rows


def trend(start, n=6, wid=None):
    months = last_months(start, n)
    key = func.strftime("%Y-%m", Transaction.date)
    q = (db.session.query(key, func.sum(Transaction.amount_cents))
         .filter(Transaction.kind == "despesa", Transaction.date >= months[0],
                 Transaction.date < month_bounds(ym(start))[1]))
    if wid:
        q = q.filter(Transaction.wallet_id == wid)
    data = dict(q.group_by(key).all())
    return [{"label": MONTHS[m.month - 1][:3], "value": data.get(ym(m), 0)} for m in months]


def wallet_balances(upto=None):
    """Saldo de cada carteira (id -> centavos): inicial + receitas - despesas +/- transferências.
    Com `upto`, considera só movimentos anteriores a essa data."""
    bal = {w.id: w.opening_cents for w in Wallet.query}
    q = (db.session.query(Transaction.wallet_id, Transaction.kind, func.sum(Transaction.amount_cents))
         .group_by(Transaction.wallet_id, Transaction.kind))
    if upto:
        q = q.filter(Transaction.date < upto)
    for wid, kind, total in q.all():
        if wid in bal:
            bal[wid] += total if kind == "receita" else -total
    for col, sign in ((Transfer.from_wallet_id, -1), (Transfer.to_wallet_id, 1)):
        q = db.session.query(col, func.sum(Transfer.amount_cents)).group_by(col)
        if upto:
            q = q.filter(Transfer.date < upto)
        for wid, total in q.all():
            if wid in bal:
                bal[wid] += sign * total
    return bal


def month_flow_by_wallet(start, nxt):
    flow = {}
    rows = (db.session.query(Transaction.wallet_id, Transaction.kind, func.sum(Transaction.amount_cents))
            .filter(Transaction.date >= start, Transaction.date < nxt)
            .group_by(Transaction.wallet_id, Transaction.kind).all())
    for wid, kind, total in rows:
        flow.setdefault(wid, {})[kind] = total
    return flow


def networth_trend(start, n=6):
    return [{"label": MONTHS[m.month - 1][:3],
             "value": sum(wallet_balances(month_bounds(ym(m))[1]).values())}
            for m in last_months(start, n)]


def migrate_db():
    """Atualiza bancos antigos: coluna wallet_id, carteira padrão e vínculo dos lançamentos."""
    cols = [r[1] for r in db.session.execute(text('PRAGMA table_info("transaction")')).fetchall()]
    if "wallet_id" not in cols:
        db.session.execute(text('ALTER TABLE "transaction" ADD COLUMN wallet_id INTEGER REFERENCES wallet(id)'))
        db.session.commit()
    if Wallet.query.count() == 0:
        db.session.add(Wallet(name="Carteira principal", kind="conta", opening_cents=0))
        db.session.commit()
    first = Wallet.query.order_by(Wallet.id).first()
    Transaction.query.filter(Transaction.wallet_id.is_(None)).update({"wallet_id": first.id})
    db.session.commit()


def insights(rows, expense, prev_expense):
    out = []
    over = [r for r in rows if r["budget"] and r["spent"] > r["budget"]]
    if over:
        r = max(over, key=lambda r: r["spent"] - r["budget"])
        out.append(f"{r['name']} está {round((r['spent'] - r['budget']) * 100 / r['budget'])}% acima do orçamento.")
    if prev_expense:
        diff = round((expense - prev_expense) * 100 / prev_expense)
        if diff > 0:
            out.append(f"Seus gastos subiram {diff}% em relação ao mês anterior.")
        elif diff < 0:
            out.append(f"Você gastou {-diff}% menos que no mês anterior.")
    if rows and rows[0]["spent"]:
        out.append(f"{rows[0]['name']} é a maior despesa do mês: {brl(rows[0]['spent'])}.")
    total_budget = sum(r["budget"] for r in rows)
    if total_budget and expense <= total_budget:
        out.append(f"Ainda restam {brl(total_budget - expense)} nos orçamentos do mês.")
    return out[:3]


def create_app():
    app = Flask(__name__)
    os.makedirs(app.instance_path, exist_ok=True)
    key_file = os.path.join(app.instance_path, "secret.key")
    if not os.path.exists(key_file):
        with open(key_file, "w") as f:
            f.write(secrets.token_hex(32))
    with open(key_file) as f:
        file_key = f.read().strip()
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///gomorrah.db",
        SECRET_KEY=os.environ.get("SECRET_KEY") or file_key,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    password = os.environ.get("GOMORRAH_PASSWORD")
    db.init_app(app)

    with app.app_context():
        db.create_all()
        if Category.query.count() == 0:
            db.session.add_all(Category(name=n) for n in DEFAULT_CATEGORIES)
            db.session.commit()
        migrate_db()

    app.add_template_filter(brl, "brl")
    app.add_template_filter(dec, "dec")
    app.add_template_filter(lambda d: f"{MONTHS[d.month - 1]} de {d.year}", "mes_ano")
    app.jinja_env.globals["WALLET_KINDS"] = WALLET_KINDS

    @app.before_request
    def guard():
        if request.method == "POST":
            sent = request.form.get("csrf", "").encode()
            if not sent or not secrets.compare_digest(sent, session.get("csrf", "").encode()):
                abort(400)
        if password and not session.get("auth") and request.endpoint not in PUBLIC:
            return redirect(url_for("login", next=request.path))

    @app.context_processor
    def inject():
        session.setdefault("csrf", secrets.token_urlsafe(16))
        return {"csrf": session["csrf"], "auth_on": bool(password)}

    # ---------- Acesso ----------
    @app.route("/entrar", methods=["GET", "POST"])
    def login():
        if not password:
            return redirect(url_for("index"))
        if request.method == "POST":
            if secrets.compare_digest(request.form.get("password", "").encode(), password.encode()):
                session.clear()
                session["auth"], session.permanent = True, True
                nxt = request.args.get("next", "")
                ok = nxt.startswith("/") and not nxt.startswith(("//", "/\\"))
                return redirect(nxt if ok else url_for("index"))
            time.sleep(1)
            flash("Senha incorreta.", "error")
        return render_template("login.html")

    @app.post("/sair")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---------- PWA ----------
    @app.route("/manifest.webmanifest")
    def manifest():
        icon = lambda n: {"src": url_for("static", filename=f"icons/icon-{n}.png"),
                          "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"}
        resp = jsonify(name="Gomorrah", short_name="Gomorrah", lang="pt-BR", start_url="/",
                       scope="/", display="standalone", background_color="#0a1530",
                       theme_color="#0a1530", icons=[icon(192), icon(512)])
        resp.mimetype = "application/manifest+json"
        return resp

    @app.route("/sw.js")
    def service_worker():
        resp = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/offline")
    def offline():
        return render_template("offline.html")

    # ---------- Painel ----------
    @app.route("/")
    def index():
        start, nxt, prev = month_bounds(request.args.get("mes"))
        wid = wallet_arg()
        income, expense = totals(start, nxt, wid)
        prev_expense = totals(prev, start, wid)[1]
        rows = sorted((r for r in category_rows(start, nxt, wid) if r["spent"] or r["budget"]),
                      key=lambda r: -r["spent"])
        total_budget = sum(r["budget"] for r in rows)
        series = trend(start, wid=wid)
        q = Transaction.query.filter(Transaction.date >= start, Transaction.date < nxt)
        if wid:
            q = q.filter(Transaction.wallet_id == wid)
        recent = q.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(5).all()
        balances = wallet_balances(nxt)
        return render_template(
            "index.html", month=start, prev=ym(prev), next=ym(nxt), income=income,
            expense=expense, balance=income - expense, rows=rows, total_budget=total_budget,
            budget_pct=round(expense * 100 / total_budget) if total_budget else 0,
            insights=insights(rows, expense, prev_expense), trend=series,
            trend_max=max([m["value"] for m in series] + [1]), recent=recent, wid=wid,
            wlist=Wallet.query.order_by(Wallet.name).all(),
            wallet_balance=balances[wid] if wid else sum(balances.values()))

    # ---------- Lançamentos ----------
    @app.route("/lancamentos")
    def transactions():
        start, nxt, prev = month_bounds(request.args.get("mes"))
        wid = wallet_arg()
        q = Transaction.query.filter(Transaction.date >= start, Transaction.date < nxt)
        if wid:
            q = q.filter(Transaction.wallet_id == wid)
        term = request.args.get("q", "").strip()
        if term:
            q = q.filter(Transaction.description.ilike(f"%{term}%"))
        kind = request.args.get("tipo", "")
        if kind in ("receita", "despesa"):
            q = q.filter(Transaction.kind == kind)
        cat = request.args.get("categoria", "")
        if cat.isdigit():
            q = q.filter(Transaction.category_id == int(cat))
        items = q.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
        return render_template(
            "transactions.html", items=items, month=start, prev=ym(prev), next=ym(nxt),
            term=term, kind=kind, cat=cat, wid=wid, categories=Category.query.order_by(Category.name).all(),
            wlist=Wallet.query.order_by(Wallet.name).all(),
            total=sum(t.amount_cents * (1 if t.kind == "receita" else -1) for t in items))

    def form_values(tx=None):
        if tx:
            return {"description": tx.description, "kind": tx.kind, "amount": dec(tx.amount_cents),
                    "date": tx.date.isoformat(), "category_id": tx.category_id or "",
                    "wallet_id": tx.wallet_id or ""}
        first = Wallet.query.order_by(Wallet.id).first()
        return {"description": "", "kind": "despesa", "amount": "", "date": date.today().isoformat(),
                "category_id": "", "wallet_id": wallet_arg() or (first.id if first else "")}

    def save(tx):
        f, errors = request.form, []
        description = f.get("description", "").strip()
        if not description:
            errors.append("Informe uma descrição.")
        try:
            cents = parse_amount(f.get("amount", ""))
        except (InvalidOperation, ValueError, OverflowError):
            errors.append("Valor inválido. Use algo como 49,90.")
        kind = f.get("kind")
        if kind not in ("receita", "despesa"):
            errors.append("Escolha receita ou despesa.")
        try:
            when = date.fromisoformat(f.get("date", ""))
        except ValueError:
            errors.append("Data inválida.")
        w_raw, cat_raw = f.get("wallet_id", ""), f.get("category_id", "")
        wallet = db.session.get(Wallet, int(w_raw)) if w_raw.isdigit() else None
        if not wallet:
            errors.append("Escolha uma carteira.")
        category = db.session.get(Category, int(cat_raw)) if cat_raw.isdigit() else None
        if errors:
            return errors
        tx.description, tx.amount_cents, tx.kind = description[:120], cents, kind
        tx.date, tx.category, tx.wallet = when, category, wallet
        db.session.add(tx)
        db.session.commit()
        return []

    def render_form(tx, title):
        values = form_values(tx) if request.method == "GET" else request.form
        return render_template("form.html", title=title, v=values,
                               categories=Category.query.order_by(Category.name).all(),
                               wlist=Wallet.query.order_by(Wallet.name).all())

    @app.route("/lancamentos/novo", methods=["GET", "POST"])
    def new_transaction():
        if request.method == "POST":
            tx = Transaction()
            errors = save(tx)
            if not errors:
                flash("Lançamento salvo.")
                return redirect(url_for("index", mes=ym(tx.date)))
            for e in errors:
                flash(e, "error")
        return render_form(None, "Novo lançamento")

    @app.route("/lancamentos/<int:tx_id>/editar", methods=["GET", "POST"])
    def edit_transaction(tx_id):
        tx = db.session.get(Transaction, tx_id) or abort(404)
        if request.method == "POST":
            errors = save(tx)
            if not errors:
                flash("Lançamento atualizado.")
                return redirect(url_for("index", mes=ym(tx.date)))
            for e in errors:
                flash(e, "error")
        return render_form(tx, "Editar lançamento")

    @app.post("/lancamentos/<int:tx_id>/excluir")
    def delete_transaction(tx_id):
        tx = db.session.get(Transaction, tx_id) or abort(404)
        month = ym(tx.date)
        db.session.delete(tx)
        db.session.commit()
        flash("Lançamento excluído.")
        return redirect(url_for("transactions", mes=month))

    # ---------- Carteiras e transferências ----------
    def save_wallet(w):
        f, errors = request.form, []
        name, kind = f.get("name", "").strip()[:50], f.get("kind")
        if not name:
            errors.append("Informe um nome para a carteira.")
        elif Wallet.query.filter(func.lower(Wallet.name) == name.lower(), Wallet.id != (w.id or 0)).first():
            errors.append("Já existe uma carteira com esse nome.")
        if kind not in WALLET_KINDS:
            errors.append("Tipo de carteira inválido.")
        raw = f.get("opening", "").strip()
        try:
            opening = parse_amount(raw, allow_zero=True) if raw else 0
        except (InvalidOperation, ValueError, OverflowError):
            errors.append("Saldo inicial inválido. Use algo como 1500,00.")
        if errors:
            return errors
        w.name, w.kind, w.opening_cents = name, kind, opening
        db.session.add(w)
        db.session.commit()
        return []

    @app.route("/carteiras")
    def wallets():
        start, nxt, prev = month_bounds(request.args.get("mes"))
        balances, flow = wallet_balances(nxt), month_flow_by_wallet(start, nxt)
        items = [{"w": w, "balance": balances[w.id], "income": flow.get(w.id, {}).get("receita", 0),
                  "expense": flow.get(w.id, {}).get("despesa", 0)} for w in Wallet.query]
        items.sort(key=lambda i: -i["balance"])
        positive = sum(max(i["balance"], 0) for i in items)
        by_kind = {}
        for n, i in enumerate(items):
            i["color"] = n % 8
            i["width"] = max(i["balance"], 0) * 100 / positive if positive else 0
            i["share"] = round(i["width"])
            by_kind[i["w"].kind] = by_kind.get(i["w"].kind, 0) + i["balance"]
        series = networth_trend(start)
        transfers = (Transfer.query.filter(Transfer.date >= start, Transfer.date < nxt)
                     .order_by(Transfer.date.desc(), Transfer.id.desc()).all())
        return render_template(
            "wallets.html", month=start, prev=ym(prev), next=ym(nxt), items=items, positive=positive,
            total=sum(i["balance"] for i in items), by_kind=by_kind, trend=series,
            trend_max=max([m["value"] for m in series] + [1]), transfers=transfers,
            income=sum(i["income"] for i in items), expense=sum(i["expense"] for i in items))

    def wallet_page(w, title):
        values = request.form if request.method == "POST" else (
            {"name": w.name, "kind": w.kind, "opening": dec(w.opening_cents)} if w.id else
            {"name": "", "kind": "conta", "opening": ""})
        return render_template("wallet_form.html", title=title, v=values, creating=not w.id)

    @app.route("/carteiras/nova", methods=["GET", "POST"])
    def new_wallet():
        w = Wallet()
        if request.method == "POST":
            errors = save_wallet(w)
            if not errors:
                flash("Carteira criada.")
                return redirect(url_for("wallets"))
            for e in errors:
                flash(e, "error")
        return wallet_page(w, "Nova carteira")

    @app.route("/carteiras/<int:wallet_id>/editar", methods=["GET", "POST"])
    def edit_wallet(wallet_id):
        w = db.session.get(Wallet, wallet_id) or abort(404)
        if request.method == "POST":
            errors = save_wallet(w)
            if not errors:
                flash("Carteira atualizada.")
                return redirect(url_for("wallets"))
            db.session.rollback()
            for e in errors:
                flash(e, "error")
        return wallet_page(w, "Editar carteira")

    @app.post("/carteiras/<int:wallet_id>/excluir")
    def delete_wallet(wallet_id):
        w = db.session.get(Wallet, wallet_id) or abort(404)
        used = (Transaction.query.filter_by(wallet_id=w.id).count()
                + Transfer.query.filter((Transfer.from_wallet_id == w.id) | (Transfer.to_wallet_id == w.id)).count())
        if used:
            flash("Essa carteira tem movimentações. Exclua ou mova-as antes.", "error")
        elif Wallet.query.count() <= 1:
            flash("Mantenha ao menos uma carteira.", "error")
        else:
            db.session.delete(w)
            db.session.commit()
            flash("Carteira excluída.")
        return redirect(url_for("wallets"))

    @app.route("/transferencias/nova", methods=["GET", "POST"])
    def new_transfer():
        if request.method == "POST":
            f, errors = request.form, []
            src = db.session.get(Wallet, int(f["from"])) if f.get("from", "").isdigit() else None
            dst = db.session.get(Wallet, int(f["to"])) if f.get("to", "").isdigit() else None
            if not src or not dst:
                errors.append("Escolha as duas carteiras.")
            elif src.id == dst.id:
                errors.append("Origem e destino precisam ser diferentes.")
            try:
                cents = parse_amount(f.get("amount", ""))
            except (InvalidOperation, ValueError, OverflowError):
                errors.append("Valor inválido. Use algo como 500,00.")
            try:
                when = date.fromisoformat(f.get("date", ""))
            except ValueError:
                errors.append("Data inválida.")
            if not errors:
                db.session.add(Transfer(from_wallet=src, to_wallet=dst, amount_cents=cents, date=when,
                                        description=f.get("description", "").strip()[:120]))
                db.session.commit()
                flash("Transferência registrada.")
                return redirect(url_for("wallets", mes=ym(when)))
            for e in errors:
                flash(e, "error")
        v = request.form if request.method == "POST" else {
            "from": "", "to": "", "amount": "", "date": date.today().isoformat(), "description": ""}
        return render_template("transfer_form.html", v=v, wlist=Wallet.query.order_by(Wallet.name).all())

    @app.post("/transferencias/<int:tr_id>/excluir")
    def delete_transfer(tr_id):
        tr = db.session.get(Transfer, tr_id) or abort(404)
        month = ym(tr.date)
        db.session.delete(tr)
        db.session.commit()
        flash("Transferência excluída.")
        return redirect(url_for("wallets", mes=month))

    # ---------- Orçamentos ----------
    @app.route("/orcamentos", methods=["GET", "POST"])
    def budgets():
        if request.method == "POST":
            start = month_bounds(request.form.get("mes"))[0]
            bad = 0
            for c in Category.query.all():
                raw = request.form.get(f"b_{c.id}", "").strip()
                try:
                    cents = parse_amount(raw, allow_zero=True) if raw else 0
                except (InvalidOperation, ValueError, OverflowError):
                    bad += 1
                    continue
                row = Budget.query.filter_by(category_id=c.id, month=ym(start)).first()
                if cents == 0 and row:
                    db.session.delete(row)
                elif cents and row:
                    row.amount_cents = cents
                elif cents:
                    db.session.add(Budget(category_id=c.id, month=ym(start), amount_cents=cents))
            db.session.commit()
            flash("Orçamento salvo." if not bad else f"Salvo, mas {bad} valor(es) inválido(s) foram ignorados.",
                  "error" if bad else "ok")
            return redirect(url_for("budgets", mes=ym(start)))
        start, nxt, prev = month_bounds(request.args.get("mes"))
        rows = [r for r in category_rows(start, nxt) if r["id"] is not None]
        return render_template("budgets.html", rows=rows, month=start, prev=ym(prev), next=ym(nxt),
                               total_budget=sum(r["budget"] for r in rows),
                               total_spent=sum(r["spent"] for r in rows))

    @app.post("/orcamentos/copiar")
    def copy_budgets():
        start, _, prev = month_bounds(request.form.get("mes"))
        have = {b.category_id for b in Budget.query.filter_by(month=ym(start))}
        copied = 0
        for b in Budget.query.filter_by(month=ym(prev)):
            if b.category_id not in have:
                db.session.add(Budget(category_id=b.category_id, month=ym(start), amount_cents=b.amount_cents))
                copied += 1
        db.session.commit()
        flash(f"{copied} orçamento(s) copiado(s) do mês anterior.")
        return redirect(url_for("budgets", mes=ym(start)))

    # ---------- Ajustes, categorias e dados ----------
    @app.route("/ajustes")
    def settings():
        usage = dict(db.session.query(Transaction.category_id, func.count(Transaction.id))
                     .group_by(Transaction.category_id).all())
        return render_template("settings.html", usage=usage,
                               categories=Category.query.order_by(Category.name).all())

    @app.post("/categorias")
    def add_category():
        name = request.form.get("name", "").strip()[:50]
        if not name:
            flash("Informe um nome para a categoria.", "error")
        elif Category.query.filter(func.lower(Category.name) == name.lower()).first():
            flash("Essa categoria já existe.", "error")
        else:
            db.session.add(Category(name=name))
            db.session.commit()
            flash("Categoria criada.")
        return redirect(url_for("settings"))

    @app.post("/categorias/<int:cat_id>/excluir")
    def delete_category(cat_id):
        cat = db.session.get(Category, cat_id) or abort(404)
        if Transaction.query.filter_by(category_id=cat.id).count():
            flash("Essa categoria tem lançamentos. Mude-os de categoria antes de excluir.", "error")
        else:
            Budget.query.filter_by(category_id=cat.id).delete()
            db.session.delete(cat)
            db.session.commit()
            flash("Categoria excluída.")
        return redirect(url_for("settings"))

    @app.route("/dados/exportar.csv")
    def export_csv():
        out = io.StringIO()
        wr = csv.writer(out)
        wr.writerow(["tipo", "data", "valor", "categoria", "descricao", "carteira", "destino"])
        money = lambda c: f"{c / 100:.2f}"
        for wl in Wallet.query.order_by(Wallet.id):
            wr.writerow(["carteira", "", money(wl.opening_cents), "", wl.kind, wl.name, ""])
        for t in Transaction.query.order_by(Transaction.date, Transaction.id):
            wr.writerow([t.kind, t.date.isoformat(), money(t.amount_cents),
                         t.category.name if t.category else "", t.description,
                         t.wallet.name if t.wallet else "", ""])
        for tr in Transfer.query.order_by(Transfer.date, Transfer.id):
            wr.writerow(["transferencia", tr.date.isoformat(), money(tr.amount_cents), "",
                         tr.description or "", tr.from_wallet.name, tr.to_wallet.name])
        for b in Budget.query.order_by(Budget.month):
            wr.writerow(["orcamento", f"{b.month}-01", money(b.amount_cents), b.category.name, "", "", ""])
        return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": f"attachment; filename=gomorrah-{date.today().isoformat()}.csv"})

    @app.post("/dados/importar")
    def import_csv():
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Escolha um arquivo CSV.", "error")
            return redirect(url_for("settings"))
        try:
            text_ = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("O arquivo precisa estar em UTF-8.", "error")
            return redirect(url_for("settings"))
        cats = {c.name.lower(): c for c in Category.query}
        wallets_by = {w.name.lower(): w for w in Wallet.query}

        def wallet_named(name):
            name = name.strip()[:50]
            if not name:
                return Wallet.query.order_by(Wallet.id).first()
            wl = wallets_by.get(name.lower())
            if not wl:
                wl = Wallet(name=name, kind="conta", opening_cents=0)
                db.session.add(wl)
                db.session.flush()
                wallets_by[name.lower()] = wl
            return wl

        ok, errors = 0, []
        for n, row in enumerate(csv.DictReader(io.StringIO(text_)), start=2):
            try:
                kind = (row.get("tipo") or "").strip().lower()
                if kind not in ("receita", "despesa", "transferencia", "orcamento", "carteira"):
                    raise Bad("tipo deve ser receita, despesa, transferencia, orcamento ou carteira")
                w_name, w_dest = (row.get("carteira") or "").strip(), (row.get("destino") or "").strip()
                if kind == "carteira":
                    if not w_name:
                        raise Bad("carteira sem nome")
                    wl = wallet_named(w_name)
                    wl.opening_cents = parse_amount(row.get("valor") or "", allow_zero=True)
                    k = (row.get("descricao") or "").strip().lower()
                    if k in WALLET_KINDS:
                        wl.kind = k
                    ok += 1
                    continue
                when = date.fromisoformat((row.get("data") or "").strip())
                cents = parse_amount(row.get("valor") or "", allow_zero=kind == "orcamento")
                name = (row.get("categoria") or "").strip()[:50]
                cat = None
                if name:
                    cat = cats.get(name.lower())
                    if not cat:
                        cat = Category(name=name)
                        db.session.add(cat)
                        db.session.flush()
                        cats[name.lower()] = cat
                if kind == "orcamento":
                    if not cat:
                        raise Bad("orçamento precisa de categoria")
                    b = Budget.query.filter_by(category_id=cat.id, month=ym(when)).first()
                    if b:
                        b.amount_cents = cents
                    else:
                        db.session.add(Budget(category_id=cat.id, month=ym(when), amount_cents=cents))
                elif kind == "transferencia":
                    if not w_name or not w_dest:
                        raise Bad("transferência precisa de carteira e destino")
                    src, dst = wallet_named(w_name), wallet_named(w_dest)
                    if src.id == dst.id:
                        raise Bad("origem e destino iguais")
                    db.session.add(Transfer(from_wallet=src, to_wallet=dst, amount_cents=cents, date=when,
                                            description=(row.get("descricao") or "").strip()[:120]))
                else:
                    desc = (row.get("descricao") or "").strip()
                    if not desc:
                        raise Bad("descrição vazia")
                    db.session.add(Transaction(description=desc[:120], amount_cents=cents, kind=kind,
                                               date=when, category=cat, wallet=wallet_named(w_name)))
                ok += 1
            except Bad as e:
                errors.append(f"linha {n}: {e}")
            except (ValueError, InvalidOperation, OverflowError):
                errors.append(f"linha {n}: data ou valor inválido")
        db.session.commit()
        msg = f"{ok} linha(s) importada(s)."
        if errors:
            msg += f" {len(errors)} com erro (" + "; ".join(errors[:4]) + (" …)" if len(errors) > 4 else ")")
        flash(msg, "error" if errors else "ok")
        return redirect(url_for("settings"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
