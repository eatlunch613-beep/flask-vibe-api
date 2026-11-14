from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, text
from extensions import db

__all__ = [
    "Account",
    "Transfer",
    "IncomeCategory",
    "Income",
    "Invoice",
    "InvoiceItem",
    "DrawPeriod",
    "DrawPrize",
]


class Account(db.Model):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('cash', 'bank', 'credit_card', 'broker')",
            name="chk_accounts_kind",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_accounts_currency",
        ),
        CheckConstraint(
            "statement_day IS NULL OR (statement_day >= 1 AND statement_day <= 31)",
            name="chk_accounts_statement_day",
        ),
        CheckConstraint(
            "payment_day IS NULL OR (payment_day >= 1 AND payment_day <= 31)",
            name="chk_accounts_payment_day",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    kind = db.Column(db.String(20), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="TWD", server_default="TWD")
    opening_balance = db.Column(
        db.Numeric(16, 2),
        nullable=False,
        default=0.00,
        server_default="0.00",
    )
    statement_day = db.Column(db.Integer, nullable=True)
    payment_day = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Transfer(db.Model):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_transfers_amount_positive"),
        CheckConstraint("fx_rate_to_twd > 0", name="chk_transfers_fx_rate_positive"),
        CheckConstraint(
            "from_account_id <> to_account_id",
            name="chk_transfers_different_accounts",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_transfers_currency",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    transferred_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(16, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(db.Numeric(12, 6), nullable=False)
    from_account_id = db.Column(
        db.BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_account_id = db.Column(
        db.BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    from_account = db.relationship(
        "Account",
        foreign_keys=[from_account_id],
        backref=db.backref("transfers_out", lazy="dynamic"),
    )
    to_account = db.relationship(
        "Account",
        foreign_keys=[to_account_id],
        backref=db.backref("transfers_in", lazy="dynamic"),
    )


class IncomeCategory(db.Model):
    __tablename__ = "income_categories"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Income(db.Model):
    __tablename__ = "incomes"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_incomes_amount_positive"),
        CheckConstraint("fx_rate_to_twd > 0", name="chk_incomes_fx_rate_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_incomes_currency",
        ),
        CheckConstraint(
            "COALESCE(TRIM(source), '') <> '' OR COALESCE(TRIM(note), '') <> ''",
            name="chk_incomes_source_or_note_not_empty",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    received_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(16, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(db.Numeric(12, 6), nullable=False)
    category_id = db.Column(
        db.BigInteger,
        ForeignKey("income_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        db.BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source = db.Column(db.String(100), nullable=True)
    note = db.Column(db.Text, nullable=True)
    invoice_id = db.Column(
        db.BigInteger,
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    category = db.relationship(
        "IncomeCategory",
        foreign_keys=[category_id],
        backref=db.backref("incomes", lazy="dynamic"),
    )
    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        backref=db.backref("incomes", lazy="dynamic"),
    )
    invoice = db.relationship(
        "Invoice",
        foreign_keys=[invoice_id],
        backref=db.backref("income", uselist=False),
    )


class Invoice(db.Model):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "number ~ '^[A-Z]{2}[0-9]{8}$'",
            name="chk_invoices_number_format",
        ),
        CheckConstraint("amount > 0", name="chk_invoices_amount_positive"),
        CheckConstraint(
            "kind IN ('paper', 'electronic')",
            name="chk_invoices_kind",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_invoices_currency",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="chk_invoices_fx_rate_positive",
        ),
        CheckConstraint(
            "random_code IS NULL OR random_code ~ '^[0-9]{4}$'",
            name="chk_invoices_random_code",
        ),
        CheckConstraint(
            "prize_status IN ('unchecked', 'lost', 'won', 'claimed', 'void')",
            name="chk_invoices_prize_status",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    number = db.Column(db.String(10), nullable=False, unique=True)
    issued_on = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    currency = db.Column(
        db.String(3),
        nullable=False,
        default="TWD",
        server_default="TWD",
    )
    fx_rate_to_twd = db.Column(db.Numeric(12, 6), nullable=False)
    random_code = db.Column(db.String(4), nullable=True)
    seller_name = db.Column(db.String(100), nullable=True)
    seller_ban = db.Column(db.String(8), nullable=True)
    prize_status = db.Column(
        db.String(20),
        nullable=False,
        default="unchecked",
        server_default="unchecked",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class InvoiceItem(db.Model):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0 AND unit_price > 0 AND line_amount > 0",
            name="chk_invoice_items_amounts_positive",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    invoice_id = db.Column(
        db.BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    line_amount = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    invoice = db.relationship(
        "Invoice",
        foreign_keys=[invoice_id],
        backref=db.backref("items", lazy="dynamic", cascade="all, delete-orphan", passive_deletes=True),
    )


class DrawPeriod(db.Model):
    __tablename__ = "draw_periods"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    period_key = db.Column(db.String(20), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DrawPrize(db.Model):
    __tablename__ = "draw_prizes"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('special', 'grand', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'extra_sixth')",
            name="chk_draw_prizes_tier",
        ),
        CheckConstraint("amount >= 0", name="chk_draw_prizes_amount_non_negative"),
        UniqueConstraint(
            "draw_period_id",
            "tier",
            "matching_number",
            name="uq_draw_prizes_period_tier_number",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    draw_period_id = db.Column(
        db.BigInteger,
        ForeignKey("draw_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier = db.Column(db.String(20), nullable=False)
    matching_number = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        server_default=text("timezone('utc', now())"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    draw_period = db.relationship(
        "DrawPeriod",
        foreign_keys=[draw_period_id],
        backref=db.backref("prizes", lazy="dynamic", cascade="all, delete-orphan", passive_deletes=True),
    )
