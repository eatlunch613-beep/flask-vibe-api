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
    "ExpenseCategory",
    "Expense",
    "Instrument",
    "Trade",
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
    trade_id = db.Column(
        db.BigInteger,
        ForeignKey("trades.id", ondelete="RESTRICT"),
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
        backref=db.backref("income", uselist=False, passive_deletes=True),
    )
    trade = db.relationship(
        "Trade",
        foreign_keys=[trade_id],
        backref=db.backref("income", uselist=False, passive_deletes=True),
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


class ExpenseCategory(db.Model):
    __tablename__ = "expense_categories"

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


class Expense(db.Model):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_expenses_amount_positive"),
        CheckConstraint("fx_rate_to_twd > 0", name="chk_expenses_fx_rate_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_expenses_currency",
        ),
        CheckConstraint(
            "COALESCE(TRIM(merchant), '') <> '' OR COALESCE(TRIM(note), '') <> ''",
            name="chk_expenses_merchant_or_note_not_empty",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    spent_on = db.Column(db.Date, nullable=False)
    settled_on = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(16, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(db.Numeric(12, 6), nullable=False)
    category_id = db.Column(
        db.BigInteger,
        ForeignKey("expense_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        db.BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merchant = db.Column(db.String(100), nullable=True)
    note = db.Column(db.Text, nullable=True)
    invoice_id = db.Column(
        db.BigInteger,
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
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
        "ExpenseCategory",
        foreign_keys=[category_id],
        backref=db.backref("expenses", lazy="dynamic"),
    )
    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        backref=db.backref("expenses", lazy="dynamic"),
    )
    invoice = db.relationship(
        "Invoice",
        foreign_keys=[invoice_id],
        backref=db.backref("expenses", lazy="dynamic", passive_deletes=True),
    )


class Instrument(db.Model):
    __tablename__ = "instruments"
    __table_args__ = (
        CheckConstraint(
            "market IN ('tw_stock', 'us_stock', 'fund', 'other')",
            name="chk_instruments_market",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_instruments_currency",
        ),
        UniqueConstraint(
            "market",
            "symbol",
            name="uq_instruments_market_symbol",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    market = db.Column(db.String(20), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    currency = db.Column(db.String(3), nullable=False)
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


class Trade(db.Model):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(
            "trade_type IN ('buy', 'sell', 'cash_dividend', 'stock_dividend', 'drip', 'split', 'merge', 'capital_reduction')",
            name="chk_trades_trade_type",
        ),
        CheckConstraint(
            "(fee IS NULL OR fee >= 0) AND (tax IS NULL OR tax >= 0)",
            name="chk_trades_fee_tax_non_negative",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="chk_trades_currency",
        ),
        CheckConstraint(
            "fx_rate_to_twd > 0",
            name="chk_trades_fx_rate_positive",
        ),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    instrument_id = db.Column(
        db.BigInteger,
        ForeignKey("instruments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id = db.Column(
        db.BigInteger,
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trade_type = db.Column(db.String(30), nullable=False)
    traded_on = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Numeric(16, 4), nullable=True)
    price = db.Column(db.Numeric(16, 4), nullable=True)
    cash_amount = db.Column(db.Numeric(16, 2), nullable=True)
    ratio = db.Column(db.Numeric(16, 6), nullable=True)
    fee = db.Column(db.Numeric(12, 2), nullable=True)
    tax = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(3), nullable=False)
    fx_rate_to_twd = db.Column(db.Numeric(12, 6), nullable=False)
    voided_at = db.Column(db.DateTime(timezone=True), nullable=True)
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

    instrument = db.relationship(
        "Instrument",
        foreign_keys=[instrument_id],
        backref=db.backref("trades", lazy="dynamic"),
    )
    account = db.relationship(
        "Account",
        foreign_keys=[account_id],
        backref=db.backref("trades", lazy="dynamic"),
    )
