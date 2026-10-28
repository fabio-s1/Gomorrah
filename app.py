import csv
import io
import os
import secrets
import time
from datetime import date
from decimal import InvalidOperation

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for, Response)
from sqlalchemy import func

from helpers import MONTHS, brl, dec, month_bounds, parse_amount
from models import Budget, Category, Transaction, db

DEFAULT_CATEGORIES = ["Moradia", "Mercado", "Transporte", "Lazer",
                      "Saúde", "Educação", "Salário", "Outros"]
PUBLIC = {"login", "static", "manifest", "service_worker", "offline"}


class Bad(Exception):
    """Erro de validação com mensagem amigável."""


def ym(d):
    return d.strftime("%Y-%m")


def totals(a, b):
    rows = dict(db.session.query(Transaction.kind, func.sum(Transaction.amount_cents))
                .filter(Transaction.date >= a, Transaction.date < b)
                .group_by(Transaction.kind).all())
    return rows.get("receita", 0), rows.get("despesa", 0)


def category_rows(start, nxt):
    """Gasto x orçamento de cada categoria no mês."""
    spent = dict(db.session.query(Transaction.category_id, func.sum(Transaction.amount_cents))
                 .filter(Transaction.kind == "despesa", Transaction.date >= start,
                         Transaction.date < nxt)
                 .group_by(Transaction.category_id).all())
    budgets = {b.category_id: b.amount_cents for b in Budget.query.filter_by(month=ym(start))}
    rows = []
    for c in Category.query.order_by(Category.name):
        s, b = spent.get(c.id, 0), budgets.get(c.id, 0)
        rows.append({"id": c.id, "name": c.name, "spent": s, "budget": b,
                     "pct": round(s * 100 / b) if b else 0})
    if spent.get(None):
        rows.append({"id": None, "name": "Sem categoria", "spent": spent[None], "budget": 0, "pct": 0})
    return rows


def trend(start, n=6):
    months = [start]
    for _ in range(n - 1):
        months.insert(0, month_bounds(ym(months[0]))[2])
    key = func.strftime("%Y-%m", Transaction.date)
    data = dict(db.session.query(key, func.sum(Transaction.amount_cents))
                .filter(Transaction.kind == "despesa", Transaction.date >= months[0],
                        Transaction.date < month_bounds(ym(start))[1])
                .group_by(key).all())
    return [{"label": MONTHS[m.month - 1][:3], "value": data.get(ym(m), 0)} for m in months]


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

    app.add_template_filter(brl, "brl")
    app.add_template_filter(dec, "dec")
    app.add_template_filter(lambda d: f"{MONTHS[d.month - 1]} de {d.year}", "mes_ano")

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
        income, expense = totals(start, nxt)
        prev_expense = totals(prev, start)[1]
        rows = sorted((r for r in category_rows(start, nxt) if r["spent"] or r["budget"]),
                      key=lambda r: -r["spent"])
        total_budget = sum(r["budget"] for r in rows)
        series = trend(start)
        recent = (Transaction.query.filter(Transaction.date >= start, Transaction.date < nxt)
                  .order_by(Transaction.date.desc(), Transaction.id.desc()).limit(5).all())
        return render_template(
            "index.html", month=start, prev=ym(prev), next=ym(nxt), income=income,
            expense=expense, balance=income - expense, rows=rows, total_budget=total_budget,
            budget_pct=round(expense * 100 / total_budget) if total_budget else 0,
            insights=insights(rows, expense, prev_expense), trend=series,
            trend_max=max([m["value"] for m in series] + [1]), recent=recent)

    # ---------- Lançamentos ----------
    @app.route("/lancamentos")
    def transactions():
        start, nxt, prev = month_bounds(request.args.get("mes"))
        q = Transaction.query.filter(Transaction.date >= start, Transaction.date < nxt)
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
            term=term, kind=kind, cat=cat, categories=Category.query.order_by(Category.name).all(),
            total=sum(t.amount_cents * (1 if t.kind == "receita" else -1) for t in items))

    def form_values(tx=None):
        if tx:
            return {"description": tx.description, "kind": tx.kind, "amount": dec(tx.amount_cents),
                    "date": tx.date.isoformat(), "category_id": tx.category_id or ""}
        return {"description": "", "kind": "despesa", "amount": "",
                "date": date.today().isoformat(), "category_id": ""}

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
        cat_raw = f.get("category_id", "")
        category = db.session.get(Category, int(cat_raw)) if cat_raw.isdigit() else None
        if errors:
            return errors
        tx.description, tx.amount_cents, tx.kind = description[:120], cents, kind
        tx.date, tx.category = when, category
        db.session.add(tx)
        db.session.commit()
        return []

    def render_form(tx, title):
        values = form_values(tx) if request.method == "GET" else request.form
        return render_template("form.html", title=title, v=values,
                               categories=Category.query.order_by(Category.name).all())

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
        w = csv.writer(out)
        w.writerow(["tipo", "data", "valor", "categoria", "descricao"])
        for t in Transaction.query.order_by(Transaction.date, Transaction.id):
            w.writerow([t.kind, t.date.isoformat(), f"{t.amount_cents / 100:.2f}",
                        t.category.name if t.category else "", t.description])
        for b in Budget.query.order_by(Budget.month):
            w.writerow(["orcamento", f"{b.month}-01", f"{b.amount_cents / 100:.2f}", b.category.name, ""])
        return Response("\ufeff" + out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": f"attachment; filename=gomorrah-{date.today().isoformat()}.csv"})

    @app.post("/dados/importar")
    def import_csv():
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Escolha um arquivo CSV.", "error")
            return redirect(url_for("settings"))
        try:
            text = f.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("O arquivo precisa estar em UTF-8.", "error")
            return redirect(url_for("settings"))
        cats = {c.name.lower(): c for c in Category.query}
        ok, errors = 0, []
        for n, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            try:
                kind = (row.get("tipo") or "").strip().lower()
                if kind not in ("receita", "despesa", "orcamento"):
                    raise Bad("tipo deve ser receita, despesa ou orcamento")
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
                else:
                    desc = (row.get("descricao") or "").strip()
                    if not desc:
                        raise Bad("descrição vazia")
                    db.session.add(Transaction(description=desc[:120], amount_cents=cents,
                                               kind=kind, date=when, category=cat))
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
