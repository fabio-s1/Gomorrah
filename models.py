from datetime import date

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)  # centavos: sem erro de float
    kind = db.Column(db.String(7), nullable=False)  # "receita" ou "despesa"
    date = db.Column(db.Date, default=date.today, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    category = db.relationship("Category")


class Budget(db.Model):
    """Orçamento mensal de uma categoria (month = 'YYYY-MM')."""
    __table_args__ = (db.UniqueConstraint("category_id", "month"),)
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    category = db.relationship("Category")
