from datetime import date

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Wallet(db.Model):
    """Carteira: conta bancária, corretora, VR/VA, dinheiro... (dinheiros separados)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    kind = db.Column(db.String(12), nullable=False, default="conta")
    opening_cents = db.Column(db.Integer, nullable=False, default=0)  # saldo inicial


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)  # centavos: sem erro de float
    kind = db.Column(db.String(7), nullable=False)  # "receita" ou "despesa"
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = db.relationship("Category")
    wallet_id = db.Column(db.Integer, db.ForeignKey("wallet.id"))
    wallet = db.relationship("Wallet")


class Transfer(db.Model):
    """Movimento entre carteiras: não conta como receita nem despesa."""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), default="")
    amount_cents = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    from_wallet_id = db.Column(db.Integer, db.ForeignKey("wallet.id"), nullable=False)
    to_wallet_id = db.Column(db.Integer, db.ForeignKey("wallet.id"), nullable=False)
    from_wallet = db.relationship("Wallet", foreign_keys=[from_wallet_id])
    to_wallet = db.relationship("Wallet", foreign_keys=[to_wallet_id])


class Budget(db.Model):
    """Orçamento mensal de uma categoria (month = 'AAAA-MM')."""
    __table_args__ = (db.UniqueConstraint("category_id", "month"),)
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    category = db.relationship("Category")
