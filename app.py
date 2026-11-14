import re
from datetime import date, datetime, timezone
import os
from pathlib import Path
from typing import Any

from decimal import Decimal
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

from extensions import db
from models import (
    Account,
    DrawPeriod,
    DrawPrize,
    Expense,
    ExpenseCategory,
    Income,
    IncomeCategory,
    Instrument,
    Invoice,
    InvoiceItem,
    Trade,
    Transfer,
)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    database_url = None
    if test_config and "SQLALCHEMY_DATABASE_URI" in test_config:
        database_url = test_config["SQLALCHEMY_DATABASE_URI"]
    elif test_config and "DATABASE_URL" in test_config:
        database_url = test_config["DATABASE_URL"]
    else:
        database_url = os.getenv("DATABASE_URL")

    if not database_url or not database_url.strip():
        raise RuntimeError("缺少環境變數 DATABASE_URL，請在環境變數或 .env 中設定 PostgreSQL 連線字串")

    clean_url = database_url.strip()
    if clean_url.startswith("postgres://"):
        clean_url = clean_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = clean_url

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    def is_allowed_origin(origin: str | None) -> bool:
        if not origin:
            return False
        if re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origin.strip()):
            return True
        web_origin = os.getenv("WEB_ORIGIN")
        if web_origin and web_origin.strip():
            allowed = [o.strip().rstrip("/") for o in web_origin.split(",") if o.strip()]
            if origin.strip().rstrip("/") in allowed:
                return True
        return False

    @app.before_request
    def handle_options_preflight():
        if request.method == "OPTIONS":
            origin = request.headers.get("Origin")
            response = app.make_default_options_response()
            if is_allowed_origin(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                req_headers = request.headers.get("Access-Control-Request-Headers")
                if req_headers:
                    response.headers["Access-Control-Allow-Headers"] = req_headers
                else:
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Private-Network"] = "true"
            response.headers["Vary"] = "Origin"
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            return response

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if is_allowed_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            req_headers = request.headers.get("Access-Control-Request-Headers")
            if req_headers:
                response.headers["Access-Control-Allow-Headers"] = req_headers
            else:
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        vary = response.headers.get("Vary")
        if vary:
            if "Origin" not in vary:
                response.headers["Vary"] = f"{vary}, Origin"
        else:
            response.headers["Vary"] = "Origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response

    def json_response(
        code: int, message: str, data: Any = None
    ) -> tuple[Any, int]:
        return jsonify(
            {"code": code, "message": message, "data": data}
        ), code

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException) -> tuple[Any, int]:
        http_status = error.code or 500
        message = "找不到這一筆" if http_status == 404 else (error.description or "請求發生錯誤")
        return json_response(http_status, message, None)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception) -> tuple[Any, int]:
        app.logger.exception("Unhandled error while processing request")
        return json_response(500, "伺服器發生未預期錯誤", None)

    @app.get("/api/health")
    def health() -> tuple[Any, int]:
        return json_response(
            200,
            "伺服器運作正常，測試正常可以進行其他任務。",
            {
                "status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.get("/api/health/db")
    def health_db() -> tuple[Any, int]:
        try:
            db.session.execute(text("SELECT 1"))
            return json_response(
                200,
                "資料庫連線正常。",
                {
                    "database": "postgresql",
                    "status": "ok",
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            app.logger.exception("Database health check failed")
            return json_response(
                500,
                "資料庫連線異常。",
                {
                    "database": "postgresql",
                    "status": "error",
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            )

    @app.get("/api/accounts")
    def list_accounts() -> tuple[Any, int]:
        accounts = Account.query.order_by(Account.id.asc()).all()
        data = [
            {
                "id": acc.id,
                "name": acc.name,
                "kind": acc.kind,
                "currency": acc.currency,
                "opening_balance": float(acc.opening_balance) if acc.opening_balance is not None else 0.0,
                "statement_day": acc.statement_day,
                "payment_day": acc.payment_day,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
            }
            for acc in accounts
        ]
        return json_response(200, "成功取得帳戶清單", data)

    @app.get("/api/accounts/<int:account_id>")
    def get_account(account_id: int) -> tuple[Any, int]:
        acc = db.session.get(Account, account_id)
        if not acc:
            return json_response(404, "找不到這一筆", None)
        data = {
            "id": acc.id,
            "name": acc.name,
            "kind": acc.kind,
            "currency": acc.currency,
            "opening_balance": float(acc.opening_balance) if acc.opening_balance is not None else 0.0,
            "statement_day": acc.statement_day,
            "payment_day": acc.payment_day,
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "updated_at": acc.updated_at.isoformat() if acc.updated_at else None,
        }
        return json_response(200, "成功取得帳戶", data)

    @app.post("/api/accounts")
    def create_account() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        kind = (body.get("kind") or "").strip()
        currency = (body.get("currency") or "TWD").strip().upper()
        opening_balance_raw = body.get("opening_balance", 0.00)
        statement_day = body.get("statement_day")
        payment_day = body.get("payment_day")

        if not name:
            return json_response(400, "帳戶名稱 (name) 為必填欄位", None)

        valid_kinds = {"cash", "bank", "credit_card", "broker"}
        if kind not in valid_kinds:
            return json_response(
                400,
                f"帳戶類型 (kind) 必須為下列其中之一: {', '.join(sorted(valid_kinds))}",
                None,
            )

        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        try:
            opening_balance = Decimal(str(opening_balance_raw))
        except Exception:
            return json_response(400, "起始餘額 (opening_balance) 格式不正確", None)

        if statement_day is not None:
            try:
                statement_day = int(statement_day)
                if not (1 <= statement_day <= 31):
                    raise ValueError()
            except (ValueError, TypeError):
                return json_response(400, "結帳日 (statement_day) 必須介於 1 到 31 之間", None)

        if payment_day is not None:
            try:
                payment_day = int(payment_day)
                if not (1 <= payment_day <= 31):
                    raise ValueError()
            except (ValueError, TypeError):
                return json_response(400, "繳款日 (payment_day) 必須介於 1 到 31 之間", None)

        existing = Account.query.filter_by(name=name).first()
        if existing:
            return json_response(400, "帳戶名稱已存在", None)

        account = Account(
            name=name,
            kind=kind,
            currency=currency,
            opening_balance=opening_balance,
            statement_day=statement_day,
            payment_day=payment_day,
        )
        db.session.add(account)
        db.session.commit()

        data = {
            "id": account.id,
            "name": account.name,
            "kind": account.kind,
            "currency": account.currency,
            "opening_balance": float(account.opening_balance),
            "statement_day": account.statement_day,
            "payment_day": account.payment_day,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }
        return json_response(200, "帳戶建立成功", data)

    @app.get("/api/accounts/<int:account_id>/balance")
    def get_account_balance(account_id: int) -> tuple[Any, int]:
        acc = db.session.get(Account, account_id)
        if not acc:
            return json_response(404, "找不到這一筆", None)

        total_balance = Decimal(str(acc.opening_balance or 0.00))

        transfers_in = Transfer.query.filter_by(to_account_id=acc.id).all()
        for t in transfers_in:
            total_balance += Decimal(str(t.amount)) * Decimal(str(t.fx_rate_to_twd))

        transfers_out = Transfer.query.filter_by(from_account_id=acc.id).all()
        for t in transfers_out:
            total_balance -= Decimal(str(t.amount)) * Decimal(str(t.fx_rate_to_twd))

        incomes = Income.query.filter_by(account_id=acc.id).all()
        for inc in incomes:
            total_balance += Decimal(str(inc.amount)) * Decimal(str(inc.fx_rate_to_twd))

        expenses = Expense.query.filter_by(account_id=acc.id).all()
        for exp in expenses:
            total_balance -= Decimal(str(exp.amount)) * Decimal(str(exp.fx_rate_to_twd))

        trades = (
            Trade.query.filter(
                Trade.account_id == acc.id,
                Trade.voided_at.is_(None),
            ).all()
        )
        for tr in trades:
            fx = Decimal(str(tr.fx_rate_to_twd))
            qty = Decimal(str(tr.quantity or 0))
            price = Decimal(str(tr.price or 0))
            fee = Decimal(str(tr.fee or 0))
            tax = Decimal(str(tr.tax or 0))

            if tr.trade_type == "buy":
                total_balance -= ((qty * price) + fee + tax) * fx
            elif tr.trade_type == "sell":
                total_balance += ((qty * price) - fee - tax) * fx
            elif tr.trade_type in ("cash_dividend", "capital_reduction"):
                if tr.cash_amount is not None:
                    if not Income.query.filter_by(trade_id=tr.id).first():
                        total_balance += Decimal(str(tr.cash_amount)) * fx

        balance_val = float(round(total_balance, 2))
        data = {
            "account_id": acc.id,
            "balance": balance_val,
            "twd_balance": balance_val,
        }
        return json_response(200, "成功取得帳戶餘額", data)

    def serialize_income_category(cat: IncomeCategory) -> dict[str, Any]:
        return {
            "id": cat.id,
            "name": cat.name,
            "description": cat.description,
            "created_at": cat.created_at.isoformat() if cat.created_at else None,
            "updated_at": cat.updated_at.isoformat() if cat.updated_at else None,
        }

    def serialize_income(inc: Income) -> dict[str, Any]:
        return {
            "id": inc.id,
            "received_on": inc.received_on.isoformat() if inc.received_on else None,
            "amount": float(inc.amount) if inc.amount is not None else 0.0,
            "currency": inc.currency,
            "fx_rate_to_twd": float(inc.fx_rate_to_twd) if inc.fx_rate_to_twd is not None else 1.0,
            "category_id": inc.category_id,
            "account_id": inc.account_id,
            "source": inc.source,
            "note": inc.note,
            "invoice_id": inc.invoice_id,
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
            "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
        }

    @app.get("/api/income-categories")
    def list_income_categories() -> tuple[Any, int]:
        categories = IncomeCategory.query.order_by(IncomeCategory.id.asc()).all()
        data = [serialize_income_category(c) for c in categories]
        return json_response(200, "成功取得入帳分類清單", data)

    @app.post("/api/income-categories")
    def create_income_category() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        description = body.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None

        if not name:
            return json_response(400, "分類名稱為必填項目", None)

        existing = IncomeCategory.query.filter_by(name=name).first()
        if existing:
            return json_response(400, "分類名稱已存在", None)

        category = IncomeCategory(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        return json_response(201, "入帳分類建立成功", serialize_income_category(category))

    @app.get("/api/income-categories/<int:category_id>")
    def get_income_category(category_id: int) -> tuple[Any, int]:
        category = db.session.get(IncomeCategory, category_id)
        if not category:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得入帳分類", serialize_income_category(category))

    @app.patch("/api/income-categories/<int:category_id>")
    def update_income_category(category_id: int) -> tuple[Any, int]:
        category = db.session.get(IncomeCategory, category_id)
        if not category:
            return json_response(404, "找不到這一筆", None)

        body = request.get_json(silent=True) or {}
        if "name" in body:
            new_name = (body.get("name") or "").strip()
            if not new_name:
                return json_response(400, "分類名稱不可為空", None)
            existing = IncomeCategory.query.filter(
                IncomeCategory.name == new_name,
                IncomeCategory.id != category_id,
            ).first()
            if existing:
                return json_response(400, "分類名稱已存在", None)
            category.name = new_name

        if "description" in body:
            desc = body.get("description")
            category.description = desc.strip() if isinstance(desc, str) and desc.strip() else None

        category.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return json_response(200, "入帳分類更新成功", serialize_income_category(category))

    @app.get("/api/incomes")
    def list_incomes() -> tuple[Any, int]:
        query = Income.query

        account_id_param = request.args.get("account_id")
        if account_id_param:
            try:
                query = query.filter(Income.account_id == int(account_id_param))
            except (ValueError, TypeError):
                return json_response(400, "帳戶編號必須為整數", None)

        category_id_param = request.args.get("category_id")
        if category_id_param:
            try:
                query = query.filter(Income.category_id == int(category_id_param))
            except (ValueError, TypeError):
                return json_response(400, "分類編號必須為整數", None)

        date_from_param = request.args.get("date_from")
        if date_from_param:
            try:
                parsed_from = date.fromisoformat(date_from_param)
                query = query.filter(Income.received_on >= parsed_from)
            except ValueError:
                return json_response(400, "起始日期格式不正確 (YYYY-MM-DD)", None)

        date_to_param = request.args.get("date_to")
        if date_to_param:
            try:
                parsed_to = date.fromisoformat(date_to_param)
                query = query.filter(Income.received_on <= parsed_to)
            except ValueError:
                return json_response(400, "結束日期格式不正確 (YYYY-MM-DD)", None)

        incomes = query.order_by(Income.received_on.desc(), Income.id.desc()).all()
        data = [serialize_income(inc) for inc in incomes]
        return json_response(200, "成功取得入帳清單", data)

    @app.post("/api/incomes")
    def create_income() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        received_on_raw = body.get("received_on")
        if not received_on_raw:
            return json_response(400, "入帳日期 (received_on) 為必填項目", None)
        try:
            received_on = date.fromisoformat(str(received_on_raw))
        except ValueError:
            return json_response(400, "入帳日期格式不正確 (YYYY-MM-DD)", None)

        amount_raw = body.get("amount")
        if amount_raw is None:
            return json_response(400, "入帳金額 (amount) 為必填項目", None)
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "入帳金額必須大於 0", None)

        currency = (body.get("currency") or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        fx_rate_raw = body.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            return json_response(400, "匯率 (fx_rate_to_twd) 為必填項目", None)
        try:
            fx_rate = Decimal(str(fx_rate_raw))
            if fx_rate <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "匯率必須大於 0", None)

        category_id_raw = body.get("category_id")
        if category_id_raw is None:
            return json_response(400, "入帳分類 (category_id) 為必填項目", None)
        try:
            category_id = int(category_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "入帳分類編號必須為整數", None)

        category = db.session.get(IncomeCategory, category_id)
        if not category:
            return json_response(400, "指定的入帳分類不存在", None)

        account_id_raw = body.get("account_id")
        if account_id_raw is None:
            return json_response(400, "帳戶 (account_id) 為必填項目", None)
        try:
            account_id = int(account_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "帳戶編號必須為整數", None)

        account = db.session.get(Account, account_id)
        if not account:
            return json_response(400, "指定的帳戶不存在", None)

        raw_source = body.get("source")
        source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None

        raw_note = body.get("note")
        note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

        if source is None and note is None:
            return json_response(400, "來源與備註不可同時為空", None)

        invoice_id_raw = body.get("invoice_id")
        invoice_id = None
        if invoice_id_raw is not None:
            try:
                invoice_id = int(invoice_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "發票編號必須為整數", None)

        income = Income(
            received_on=received_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate,
            category_id=category_id,
            account_id=account_id,
            source=source,
            note=note,
            invoice_id=invoice_id,
        )
        db.session.add(income)
        db.session.commit()

        return json_response(201, "入帳建立成功", serialize_income(income))

    @app.get("/api/incomes/<int:income_id>")
    def get_income(income_id: int) -> tuple[Any, int]:
        income = db.session.get(Income, income_id)
        if not income:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得入帳資料", serialize_income(income))

    @app.patch("/api/incomes/<int:income_id>")
    def update_income(income_id: int) -> tuple[Any, int]:
        income = db.session.get(Income, income_id)
        if not income:
            return json_response(404, "找不到這一筆", None)

        body = request.get_json(silent=True) or {}

        if "received_on" in body:
            received_on_raw = body.get("received_on")
            if not received_on_raw:
                return json_response(400, "入帳日期不可為空", None)
            try:
                income.received_on = date.fromisoformat(str(received_on_raw))
            except ValueError:
                return json_response(400, "入帳日期格式不正確 (YYYY-MM-DD)", None)

        if "amount" in body:
            amount_raw = body.get("amount")
            if amount_raw is None:
                return json_response(400, "入帳金額不可為空", None)
            try:
                amount = Decimal(str(amount_raw))
                if amount <= 0:
                    raise ValueError()
                income.amount = amount
            except Exception:
                return json_response(400, "入帳金額必須大於 0", None)

        if "currency" in body:
            currency = (body.get("currency") or "").strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)
            income.currency = currency

        if "fx_rate_to_twd" in body:
            fx_rate_raw = body.get("fx_rate_to_twd")
            if fx_rate_raw is None:
                return json_response(400, "匯率不可為空", None)
            try:
                fx_rate = Decimal(str(fx_rate_raw))
                if fx_rate <= 0:
                    raise ValueError()
                income.fx_rate_to_twd = fx_rate
            except Exception:
                return json_response(400, "匯率必須大於 0", None)

        if "category_id" in body:
            cat_id_raw = body.get("category_id")
            try:
                cat_id = int(cat_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "入帳分類編號必須為整數", None)
            category = db.session.get(IncomeCategory, cat_id)
            if not category:
                return json_response(400, "指定的入帳分類不存在", None)
            income.category_id = cat_id

        if "account_id" in body:
            acc_id_raw = body.get("account_id")
            try:
                acc_id = int(acc_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "帳戶編號必須為整數", None)
            account = db.session.get(Account, acc_id)
            if not account:
                return json_response(400, "指定的帳戶不存在", None)
            income.account_id = acc_id

        # Update source and note if present in payload
        candidate_source = income.source
        candidate_note = income.note

        if "source" in body:
            raw_source = body.get("source")
            candidate_source = raw_source.strip() if isinstance(raw_source, str) and raw_source.strip() else None

        if "note" in body:
            raw_note = body.get("note")
            candidate_note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

        if candidate_source is None and candidate_note is None:
            return json_response(400, "來源與備註不可同時為空", None)

        income.source = candidate_source
        income.note = candidate_note
        income.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return json_response(200, "入帳更新成功", serialize_income(income))

    def serialize_expense_category(cat: ExpenseCategory) -> dict[str, Any]:
        return {
            "id": cat.id,
            "name": cat.name,
            "description": cat.description,
            "created_at": cat.created_at.isoformat() if cat.created_at else None,
            "updated_at": cat.updated_at.isoformat() if cat.updated_at else None,
        }

    def serialize_expense(exp: Expense) -> dict[str, Any]:
        return {
            "id": exp.id,
            "spent_on": exp.spent_on.isoformat() if exp.spent_on else None,
            "settled_on": exp.settled_on.isoformat() if exp.settled_on else None,
            "amount": float(exp.amount) if exp.amount is not None else 0.0,
            "currency": exp.currency,
            "fx_rate_to_twd": float(exp.fx_rate_to_twd) if exp.fx_rate_to_twd is not None else 1.0,
            "category_id": exp.category_id,
            "account_id": exp.account_id,
            "merchant": exp.merchant,
            "note": exp.note,
            "invoice_id": exp.invoice_id,
            "created_at": exp.created_at.isoformat() if exp.created_at else None,
            "updated_at": exp.updated_at.isoformat() if exp.updated_at else None,
        }

    @app.get("/api/expense-categories")
    def list_expense_categories() -> tuple[Any, int]:
        categories = ExpenseCategory.query.order_by(ExpenseCategory.id.asc()).all()
        data = [serialize_expense_category(c) for c in categories]
        return json_response(200, "成功取得花費分類清單", data)

    @app.post("/api/expense-categories")
    def create_expense_category() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        description = body.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None

        if not name:
            return json_response(400, "分類名稱為必填項目", None)

        existing = ExpenseCategory.query.filter_by(name=name).first()
        if existing:
            return json_response(400, "分類名稱已存在", None)

        category = ExpenseCategory(name=name, description=description)
        db.session.add(category)
        db.session.commit()
        return json_response(201, "花費分類建立成功", serialize_expense_category(category))

    @app.get("/api/expense-categories/<int:category_id>")
    def get_expense_category(category_id: int) -> tuple[Any, int]:
        category = db.session.get(ExpenseCategory, category_id)
        if not category:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得花費分類", serialize_expense_category(category))

    @app.patch("/api/expense-categories/<int:category_id>")
    def update_expense_category(category_id: int) -> tuple[Any, int]:
        category = db.session.get(ExpenseCategory, category_id)
        if not category:
            return json_response(404, "找不到這一筆", None)

        body = request.get_json(silent=True) or {}
        if "name" in body:
            new_name = (body.get("name") or "").strip()
            if not new_name:
                return json_response(400, "分類名稱不可為空", None)
            existing = ExpenseCategory.query.filter(
                ExpenseCategory.name == new_name,
                ExpenseCategory.id != category_id,
            ).first()
            if existing:
                return json_response(400, "分類名稱已存在", None)
            category.name = new_name

        if "description" in body:
            desc = body.get("description")
            category.description = desc.strip() if isinstance(desc, str) and desc.strip() else None

        category.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return json_response(200, "花費分類更新成功", serialize_expense_category(category))

    @app.get("/api/expenses")
    def list_expenses() -> tuple[Any, int]:
        query = Expense.query

        account_id_param = request.args.get("account_id")
        if account_id_param:
            try:
                query = query.filter(Expense.account_id == int(account_id_param))
            except (ValueError, TypeError):
                return json_response(400, "帳戶編號必須為整數", None)

        category_id_param = request.args.get("category_id")
        if category_id_param:
            try:
                query = query.filter(Expense.category_id == int(category_id_param))
            except (ValueError, TypeError):
                return json_response(400, "分類編號必須為整數", None)

        invoice_id_param = request.args.get("invoice_id")
        if invoice_id_param:
            try:
                query = query.filter(Expense.invoice_id == int(invoice_id_param))
            except (ValueError, TypeError):
                return json_response(400, "發票編號必須為整數", None)

        date_from_param = request.args.get("date_from")
        if date_from_param:
            try:
                parsed_from = date.fromisoformat(date_from_param)
                query = query.filter(Expense.spent_on >= parsed_from)
            except ValueError:
                return json_response(400, "起始日期格式不正確 (YYYY-MM-DD)", None)

        date_to_param = request.args.get("date_to")
        if date_to_param:
            try:
                parsed_to = date.fromisoformat(date_to_param)
                query = query.filter(Expense.spent_on <= parsed_to)
            except ValueError:
                return json_response(400, "結束日期格式不正確 (YYYY-MM-DD)", None)

        expenses = query.order_by(Expense.spent_on.desc(), Expense.id.desc()).all()
        data = [serialize_expense(exp) for exp in expenses]
        return json_response(200, "成功取得花費清單", data)

    @app.post("/api/expenses")
    def create_expense() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        spent_on_raw = body.get("spent_on")
        if not spent_on_raw:
            return json_response(400, "消費日期 (spent_on) 為必填項目", None)
        try:
            spent_on = date.fromisoformat(str(spent_on_raw))
        except ValueError:
            return json_response(400, "消費日期格式不正確 (YYYY-MM-DD)", None)

        settled_on_raw = body.get("settled_on")
        settled_on = None
        if settled_on_raw is not None:
            try:
                settled_on = date.fromisoformat(str(settled_on_raw))
            except ValueError:
                return json_response(400, "結算日期格式不正確 (YYYY-MM-DD)", None)

        amount_raw = body.get("amount")
        if amount_raw is None:
            return json_response(400, "花費金額 (amount) 為必填項目", None)
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "花費金額必須大於 0", None)

        currency = (body.get("currency") or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        fx_rate_raw = body.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            return json_response(400, "匯率 (fx_rate_to_twd) 為必填項目", None)
        try:
            fx_rate = Decimal(str(fx_rate_raw))
            if fx_rate <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "匯率必須大於 0", None)

        category_id_raw = body.get("category_id")
        if category_id_raw is None:
            return json_response(400, "花費分類 (category_id) 為必填項目", None)
        try:
            category_id = int(category_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "花費分類編號必須為整數", None)

        category = db.session.get(ExpenseCategory, category_id)
        if not category:
            return json_response(400, "指名的花費分類不存在", None)

        account_id_raw = body.get("account_id")
        if account_id_raw is None:
            return json_response(400, "帳戶 (account_id) 為必填項目", None)
        try:
            account_id = int(account_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "帳戶編號必須為整數", None)

        account = db.session.get(Account, account_id)
        if not account:
            return json_response(400, "指名的帳戶不存在", None)

        raw_merchant = body.get("merchant")
        merchant = raw_merchant.strip() if isinstance(raw_merchant, str) and raw_merchant.strip() else None

        raw_note = body.get("note")
        note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

        if merchant is None and note is None:
            return json_response(400, "商家與備註不可同時為空", None)

        invoice_id_raw = body.get("invoice_id")
        invoice_id = None
        if invoice_id_raw is not None:
            try:
                invoice_id = int(invoice_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "發票編號必須為整數", None)

            inv = db.session.get(Invoice, invoice_id)
            if not inv:
                return json_response(400, "指名的發票不存在", None)

        expense = Expense(
            spent_on=spent_on,
            settled_on=settled_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate,
            category_id=category_id,
            account_id=account_id,
            merchant=merchant,
            note=note,
            invoice_id=invoice_id,
        )
        db.session.add(expense)
        db.session.commit()

        return json_response(201, "花費建立成功", serialize_expense(expense))

    @app.get("/api/expenses/<int:expense_id>")
    def get_expense(expense_id: int) -> tuple[Any, int]:
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得花費資料", serialize_expense(expense))

    @app.patch("/api/expenses/<int:expense_id>")
    def update_expense(expense_id: int) -> tuple[Any, int]:
        expense = db.session.get(Expense, expense_id)
        if not expense:
            return json_response(404, "找不到這一筆", None)

        body = request.get_json(silent=True) or {}

        if "spent_on" in body:
            spent_on_raw = body.get("spent_on")
            if not spent_on_raw:
                return json_response(400, "消費日期不可為空", None)
            try:
                expense.spent_on = date.fromisoformat(str(spent_on_raw))
            except ValueError:
                return json_response(400, "消費日期格式不正確 (YYYY-MM-DD)", None)

        if "settled_on" in body:
            settled_on_raw = body.get("settled_on")
            if settled_on_raw is None or str(settled_on_raw).strip() == "":
                expense.settled_on = None
            else:
                try:
                    expense.settled_on = date.fromisoformat(str(settled_on_raw))
                except ValueError:
                    return json_response(400, "結算日期格式不正確 (YYYY-MM-DD)", None)

        if "amount" in body:
            amount_raw = body.get("amount")
            if amount_raw is None:
                return json_response(400, "花費金額不可為空", None)
            try:
                amount = Decimal(str(amount_raw))
                if amount <= 0:
                    raise ValueError()
                expense.amount = amount
            except Exception:
                return json_response(400, "花費金額必須大於 0", None)

        if "currency" in body:
            currency = (body.get("currency") or "").strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)
            expense.currency = currency

        if "fx_rate_to_twd" in body:
            fx_rate_raw = body.get("fx_rate_to_twd")
            if fx_rate_raw is None:
                return json_response(400, "匯率不可為空", None)
            try:
                fx_rate = Decimal(str(fx_rate_raw))
                if fx_rate <= 0:
                    raise ValueError()
                expense.fx_rate_to_twd = fx_rate
            except Exception:
                return json_response(400, "匯率必須大於 0", None)

        if "category_id" in body:
            cat_id_raw = body.get("category_id")
            try:
                cat_id = int(cat_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "花費分類編號必須為整數", None)
            category = db.session.get(ExpenseCategory, cat_id)
            if not category:
                return json_response(400, "指名的花費分類不存在", None)
            expense.category_id = cat_id

        if "account_id" in body:
            acc_id_raw = body.get("account_id")
            try:
                acc_id = int(acc_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "帳戶編號必須為整數", None)
            account = db.session.get(Account, acc_id)
            if not account:
                return json_response(400, "指名的帳戶不存在", None)
            expense.account_id = acc_id

        if "invoice_id" in body:
            inv_id_raw = body.get("invoice_id")
            if inv_id_raw is None:
                expense.invoice_id = None
            else:
                try:
                    inv_id = int(inv_id_raw)
                except (ValueError, TypeError):
                    return json_response(400, "發票編號必須為整數", None)
                inv = db.session.get(Invoice, inv_id)
                if not inv:
                    return json_response(400, "指名的發票不存在", None)
                expense.invoice_id = inv_id

        # Update merchant and note if present in payload
        candidate_merchant = expense.merchant
        candidate_note = expense.note

        if "merchant" in body:
            raw_merchant = body.get("merchant")
            candidate_merchant = raw_merchant.strip() if isinstance(raw_merchant, str) and raw_merchant.strip() else None

        if "note" in body:
            raw_note = body.get("note")
            candidate_note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

        if candidate_merchant is None and candidate_note is None:
            return json_response(400, "商家與備註不可同時為空", None)

        expense.merchant = candidate_merchant
        expense.note = candidate_note
        expense.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return json_response(200, "花費更新成功", serialize_expense(expense))

    def get_invoice_period_key(issued_on: date) -> str:
        start_month = ((issued_on.month - 1) // 2) * 2 + 1
        return f"{issued_on.year}-{start_month:02d}"

    def get_period_date_range(period_key: str) -> tuple[date, date]:
        parts = period_key.strip().split("-")
        year = int(parts[0])
        start_month = int(parts[1])
        start_date = date(year, start_month, 1)
        end_month = start_month + 1
        if end_month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif end_month in (4, 6, 9, 11):
            last_day = 30
        else:
            is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
            last_day = 29 if is_leap else 28
        end_date = date(year, end_month, last_day)
        return start_date, end_date

    def serialize_invoice(inv: Invoice, include_details: bool = False) -> dict[str, Any]:
        data = {
            "id": inv.id,
            "number": inv.number,
            "issued_on": inv.issued_on.isoformat() if inv.issued_on else None,
            "amount": float(inv.amount) if inv.amount is not None else 0.0,
            "kind": inv.kind,
            "currency": inv.currency,
            "fx_rate_to_twd": float(inv.fx_rate_to_twd) if inv.fx_rate_to_twd is not None else 1.0,
            "random_code": inv.random_code,
            "seller_name": inv.seller_name,
            "seller_ban": inv.seller_ban,
            "prize_status": inv.prize_status,
            "period_key": get_invoice_period_key(inv.issued_on) if inv.issued_on else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        }
        if include_details:
            data["items"] = [
                {
                    "id": item.id,
                    "invoice_id": item.invoice_id,
                    "name": item.name,
                    "quantity": float(item.quantity) if item.quantity is not None else 0.0,
                    "unit_price": float(item.unit_price) if item.unit_price is not None else 0.0,
                    "line_amount": float(item.line_amount) if item.line_amount is not None else 0.0,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in inv.items
            ]
            data["expense_ids"] = [e.id for e in inv.expenses]
        return data

    def serialize_invoice_item(item: InvoiceItem) -> dict[str, Any]:
        return {
            "id": item.id,
            "invoice_id": item.invoice_id,
            "name": item.name,
            "quantity": float(item.quantity) if item.quantity is not None else 0.0,
            "unit_price": float(item.unit_price) if item.unit_price is not None else 0.0,
            "line_amount": float(item.line_amount) if item.line_amount is not None else 0.0,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def serialize_draw_period(dp: DrawPeriod) -> dict[str, Any]:
        return {
            "id": dp.id,
            "period_key": dp.period_key,
            "created_at": dp.created_at.isoformat() if dp.created_at else None,
            "updated_at": dp.updated_at.isoformat() if dp.updated_at else None,
        }

    def serialize_draw_prize(prize: DrawPrize) -> dict[str, Any]:
        return {
            "id": prize.id,
            "draw_period_id": prize.draw_period_id,
            "tier": prize.tier,
            "matching_number": prize.matching_number,
            "amount": float(prize.amount) if prize.amount is not None else 0.0,
            "created_at": prize.created_at.isoformat() if prize.created_at else None,
            "updated_at": prize.updated_at.isoformat() if prize.updated_at else None,
        }

    def check_prize_match(digits: str, prize: DrawPrize) -> bool:
        tier = prize.tier
        mn = prize.matching_number
        if tier in ("special", "grand", "first"):
            return digits == mn
        elif tier == "second":
            return digits[-7:] == mn[-7:]
        elif tier == "third":
            return digits[-6:] == mn[-6:]
        elif tier == "fourth":
            return digits[-5:] == mn[-5:]
        elif tier == "fifth":
            return digits[-4:] == mn[-4:]
        elif tier in ("sixth", "extra_sixth"):
            return digits[-3:] == mn[-3:]
        return False

    @app.post("/api/invoices")
    def create_invoice() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        number = (body.get("number") or "").strip().upper()
        if not number or not re.match(r"^[A-Z]{2}[0-9]{8}$", number):
            return json_response(400, "發票號碼格式不符合（需為 2 碼大寫英文字母加 8 碼數字）", None)

        existing = Invoice.query.filter_by(number=number).first()
        if existing:
            return json_response(400, "發票號碼已存在", None)

        issued_on_raw = body.get("issued_on")
        if not issued_on_raw:
            return json_response(400, "發票開立日 (issued_on) 為必填項目", None)
        try:
            issued_on = date.fromisoformat(str(issued_on_raw))
        except ValueError:
            return json_response(400, "開立日期格式不正確 (YYYY-MM-DD)", None)

        amount_raw = body.get("amount")
        if amount_raw is None:
            return json_response(400, "發票金額 (amount) 為必填項目", None)
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "發票金額必須大於 0", None)

        kind = (body.get("kind") or "").strip().lower()
        if kind not in ("paper", "electronic"):
            return json_response(400, "發票種類 (kind) 必須為 paper 或 electronic", None)

        currency = (body.get("currency") or "TWD").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        fx_rate_raw = body.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            if currency == "TWD":
                fx_rate = Decimal("1.000000")
            else:
                return json_response(400, "外幣發票之換算匯率 (fx_rate_to_twd) 為必填項目", None)
        else:
            try:
                fx_rate = Decimal(str(fx_rate_raw))
                if fx_rate <= 0:
                    raise ValueError()
            except Exception:
                return json_response(400, "換算匯率必須大於 0", None)

        random_code_raw = body.get("random_code")
        random_code = None
        if random_code_raw is not None and str(random_code_raw).strip():
            rc_str = str(random_code_raw).strip()
            if not re.match(r"^[0-9]{4}$", rc_str):
                return json_response(400, "隨機碼必須為 4 碼數字", None)
            random_code = rc_str

        raw_seller_name = body.get("seller_name")
        seller_name = raw_seller_name.strip() if isinstance(raw_seller_name, str) and raw_seller_name.strip() else None

        raw_seller_ban = body.get("seller_ban")
        seller_ban = raw_seller_ban.strip() if isinstance(raw_seller_ban, str) and raw_seller_ban.strip() else None

        inv = Invoice(
            number=number,
            issued_on=issued_on,
            amount=amount,
            kind=kind,
            currency=currency,
            fx_rate_to_twd=fx_rate,
            random_code=random_code,
            seller_name=seller_name,
            seller_ban=seller_ban,
            prize_status="unchecked",
        )
        db.session.add(inv)
        db.session.commit()

        return json_response(201, "發票建立成功", serialize_invoice(inv))

    @app.get("/api/invoices")
    def list_invoices() -> tuple[Any, int]:
        query = Invoice.query

        period_key = request.args.get("period_key")
        if period_key:
            try:
                start_date, end_date = get_period_date_range(period_key)
                query = query.filter(Invoice.issued_on >= start_date, Invoice.issued_on <= end_date)
            except Exception:
                return json_response(400, "期別格式不正確 (需為 YYYY-MM，如 2026-01)", None)

        prize_status = request.args.get("prize_status")
        if prize_status:
            query = query.filter(Invoice.prize_status == prize_status.strip().lower())

        invoices = query.order_by(Invoice.issued_on.desc(), Invoice.id.desc()).all()
        data = [serialize_invoice(inv) for inv in invoices]
        return json_response(200, "成功取得發票清單", data)

    @app.get("/api/invoices/<int:invoice_id>")
    def get_invoice(invoice_id: int) -> tuple[Any, int]:
        inv = db.session.get(Invoice, invoice_id)
        if not inv:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得發票資料", serialize_invoice(inv, include_details=True))

    @app.patch("/api/invoices/<int:invoice_id>")
    def update_invoice(invoice_id: int) -> tuple[Any, int]:
        inv = db.session.get(Invoice, invoice_id)
        if not inv:
            return json_response(404, "找不到這一筆", None)

        body = request.get_json(silent=True) or {}

        if "seller_name" in body:
            raw_name = body.get("seller_name")
            inv.seller_name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None

        if "seller_ban" in body:
            raw_ban = body.get("seller_ban")
            inv.seller_ban = raw_ban.strip() if isinstance(raw_ban, str) and raw_ban.strip() else None

        if "random_code" in body:
            rc_raw = body.get("random_code")
            if rc_raw is None or str(rc_raw).strip() == "":
                inv.random_code = None
            else:
                rc_str = str(rc_raw).strip()
                if not re.match(r"^[0-9]{4}$", rc_str):
                    return json_response(400, "隨機碼必須為 4 碼數字", None)
                inv.random_code = rc_str

        if "prize_status" in body:
            ps_raw = (body.get("prize_status") or "").strip().lower()
            if ps_raw != "void":
                return json_response(400, "目前僅允許將兌獎狀態改為 void (作廢)", None)
            inv.prize_status = "void"

        inv.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return json_response(200, "發票更新成功", serialize_invoice(inv, include_details=True))

    @app.post("/api/invoices/<int:invoice_id>/items")
    def create_invoice_item(invoice_id: int) -> tuple[Any, int]:
        inv = db.session.get(Invoice, invoice_id)
        if not inv:
            return json_response(400, "指名的發票不存在", None)

        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return json_response(400, "品項名稱 (name) 為必填項目", None)

        qty_raw = body.get("quantity")
        price_raw = body.get("unit_price")
        amount_raw = body.get("line_amount")

        if qty_raw is None or price_raw is None or amount_raw is None:
            return json_response(400, "數量 (quantity)、單價 (unit_price) 與小計 (line_amount) 為必填項目", None)

        try:
            quantity = Decimal(str(qty_raw))
            unit_price = Decimal(str(price_raw))
            line_amount = Decimal(str(amount_raw))
            if quantity <= 0 or unit_price <= 0 or line_amount <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "品項數量、單價與小計皆必須大於 0", None)

        item = InvoiceItem(
            invoice_id=inv.id,
            name=name,
            quantity=quantity,
            unit_price=unit_price,
            line_amount=line_amount,
        )
        db.session.add(item)
        db.session.commit()
        return json_response(201, "發票品項建立成功", serialize_invoice_item(item))

    @app.get("/api/invoices/<int:invoice_id>/items")
    def list_invoice_items(invoice_id: int) -> tuple[Any, int]:
        inv = db.session.get(Invoice, invoice_id)
        if not inv:
            return json_response(404, "找不到這一筆", None)
        items = InvoiceItem.query.filter_by(invoice_id=inv.id).order_by(InvoiceItem.id.asc()).all()
        return json_response(200, "成功取得發票品項清單", [serialize_invoice_item(it) for it in items])

    @app.post("/api/draw-periods")
    def create_draw_period() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}
        period_key = (body.get("period_key") or "").strip()
        if not period_key or not re.match(r"^[0-9]{4}-(01|03|05|07|09|11)$", period_key):
            return json_response(400, "期別 (period_key) 格式不符合（需為 YYYY-MM，如 2026-01）", None)

        existing = DrawPeriod.query.filter_by(period_key=period_key).first()
        if existing:
            return json_response(400, "此開獎期別已存在", None)

        dp = DrawPeriod(period_key=period_key)
        db.session.add(dp)
        db.session.commit()
        return json_response(201, "開獎期別建立成功", serialize_draw_period(dp))

    @app.post("/api/draw-periods/<int:period_id>/prizes")
    def create_draw_prize(period_id: int) -> tuple[Any, int]:
        dp = db.session.get(DrawPeriod, period_id)
        if not dp:
            return json_response(400, "指名的開獎期別不存在", None)

        body = request.get_json(silent=True) or {}
        tier = (body.get("tier") or "").strip().lower()
        valid_tiers = {
            "special", "grand", "first", "second", "third",
            "fourth", "fifth", "sixth", "extra_sixth",
        }
        if tier not in valid_tiers:
            return json_response(400, f"獎項類別 (tier) 不正確，必須為下列之一: {', '.join(sorted(valid_tiers))}", None)

        mn = (body.get("matching_number") or "").strip()
        if not mn:
            return json_response(400, "中獎號碼 (matching_number) 為必填項目", None)

        if tier in ("special", "grand", "first"):
            if len(mn) != 8 or not mn.isdigit():
                return json_response(400, "特別獎、特獎與頭獎的號碼必須為 8 碼數字", None)
        else:
            if not mn.isdigit():
                return json_response(400, "中獎號碼必須全為數字", None)

        amount_raw = body.get("amount")
        if amount_raw is None:
            return json_response(400, "獎金金額 (amount) 為必填項目", None)
        try:
            amount = Decimal(str(amount_raw))
            if amount < 0:
                raise ValueError()
        except Exception:
            return json_response(400, "獎金金額必須大於或等於 0", None)

        existing = DrawPrize.query.filter_by(
            draw_period_id=dp.id,
            tier=tier,
            matching_number=mn,
        ).first()
        if existing:
            return json_response(400, "該期已存在相同獎項與獎號", None)

        prize = DrawPrize(
            draw_period_id=dp.id,
            tier=tier,
            matching_number=mn,
            amount=amount,
        )
        db.session.add(prize)
        db.session.commit()
        return json_response(201, "開獎獎項建立成功", serialize_draw_prize(prize))

    @app.post("/api/draw-periods/<int:period_id>/check")
    def check_draw_period(period_id: int) -> tuple[Any, int]:
        dp = db.session.get(DrawPeriod, period_id)
        if not dp:
            return json_response(400, "指名的開獎期別不存在", None)

        prizes = DrawPrize.query.filter_by(draw_period_id=dp.id).all()
        start_date, end_date = get_period_date_range(dp.period_key)

        invoices = Invoice.query.filter(
            Invoice.issued_on >= start_date,
            Invoice.issued_on <= end_date,
            Invoice.prize_status != "void",
        ).all()

        checked_count = len(invoices)
        won_count = 0

        for inv in invoices:
            digits = inv.number[2:]
            matched = [p for p in prizes if check_prize_match(digits, p)]
            if matched:
                inv.prize_status = "won"
                won_count += 1
            else:
                inv.prize_status = "lost"
            inv.updated_at = datetime.now(timezone.utc)

        db.session.commit()
        return json_response(200, "對獎完成", {"checked_count": checked_count, "won_count": won_count})

    @app.post("/api/invoices/<int:invoice_id>/prize-income")
    def claim_prize_income(invoice_id: int) -> tuple[Any, int]:
        inv = db.session.get(Invoice, invoice_id)
        if not inv:
            return json_response(404, "找不到這一筆", None)

        if inv.prize_status != "won":
            return json_response(400, "只有中獎 (won) 的發票才能領獎入帳", None)

        existing_income = Income.query.filter_by(invoice_id=inv.id).first()
        if existing_income:
            return json_response(400, "此發票已領過獎並已入帳", None)

        body = request.get_json(silent=True) or {}
        cat_id_raw = body.get("category_id")
        acc_id_raw = body.get("account_id")

        if cat_id_raw is None or acc_id_raw is None:
            return json_response(400, "入帳分類 (category_id) 與帳戶 (account_id) 為必填項目", None)

        try:
            category_id = int(cat_id_raw)
            account_id = int(acc_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "分類與帳戶編號必須為整數", None)

        category = db.session.get(IncomeCategory, category_id)
        if not category:
            return json_response(400, "指名的入帳分類不存在", None)

        account = db.session.get(Account, account_id)
        if not account:
            return json_response(400, "指名的帳戶不存在", None)

        period_key = get_invoice_period_key(inv.issued_on)
        dp = DrawPeriod.query.filter_by(period_key=period_key).first()
        if not dp:
            return json_response(400, "找不到對應開獎期的獎金資料", None)

        digits = inv.number[2:]
        matched = [p for p in dp.prizes if check_prize_match(digits, p)]
        if not matched:
            return json_response(400, "該發票未比對到中獎獎項", None)

        best_prize = max(matched, key=lambda p: p.amount)
        prize_amount = best_prize.amount

        try:
            income = Income(
                received_on=date.today(),
                amount=prize_amount,
                currency=inv.currency,
                fx_rate_to_twd=inv.fx_rate_to_twd,
                category_id=category_id,
                account_id=account_id,
                source=f"統一發票中獎 {inv.number}",
                note=f"統一發票中獎獎金",
                invoice_id=inv.id,
            )
            db.session.add(income)
            inv.prize_status = "claimed"
            inv.updated_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return json_response(201, "中獎入帳建立成功", serialize_income(income))

    def serialize_instrument(inst: Instrument) -> dict[str, Any]:
        return {
            "id": inst.id,
            "market": inst.market,
            "symbol": inst.symbol,
            "name": inst.name,
            "currency": inst.currency,
            "created_at": inst.created_at.isoformat() if inst.created_at else None,
            "updated_at": inst.updated_at.isoformat() if inst.updated_at else None,
        }

    def serialize_trade(tr: Trade) -> dict[str, Any]:
        return {
            "id": tr.id,
            "instrument_id": tr.instrument_id,
            "account_id": tr.account_id,
            "trade_type": tr.trade_type,
            "traded_on": tr.traded_on.isoformat() if tr.traded_on else None,
            "quantity": float(tr.quantity) if tr.quantity is not None else None,
            "price": float(tr.price) if tr.price is not None else None,
            "cash_amount": float(tr.cash_amount) if tr.cash_amount is not None else None,
            "ratio": float(tr.ratio) if tr.ratio is not None else None,
            "fee": float(tr.fee) if tr.fee is not None else None,
            "tax": float(tr.tax) if tr.tax is not None else None,
            "currency": tr.currency,
            "fx_rate_to_twd": float(tr.fx_rate_to_twd) if tr.fx_rate_to_twd is not None else 1.0,
            "voided_at": tr.voided_at.isoformat() if tr.voided_at else None,
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
            "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
        }

    def compute_instrument_holding(instrument_id: int) -> tuple[Decimal, Decimal]:
        trades = (
            Trade.query.filter(
                Trade.instrument_id == instrument_id,
                Trade.voided_at.is_(None),
            )
            .order_by(Trade.traded_on.asc(), Trade.id.asc())
            .all()
        )

        total_shares = Decimal("0")
        total_cost = Decimal("0")

        for tr in trades:
            ttype = tr.trade_type
            if ttype in ("buy", "drip"):
                q = Decimal(str(tr.quantity or 0))
                p = Decimal(str(tr.price or 0))
                total_shares += q
                total_cost += q * p
            elif ttype == "stock_dividend":
                q = Decimal(str(tr.quantity or 0))
                total_shares += q
            elif ttype in ("split", "merge"):
                if tr.ratio is not None:
                    r = Decimal(str(tr.ratio))
                    total_shares = total_shares * r
            elif ttype == "sell":
                q = Decimal(str(tr.quantity or 0))
                if total_shares > 0:
                    avg_cost = total_cost / total_shares
                    total_cost = max(Decimal("0"), total_cost - (q * avg_cost))
                    total_shares = max(Decimal("0"), total_shares - q)
                else:
                    total_shares = Decimal("0")
                    total_cost = Decimal("0")
            elif ttype == "capital_reduction":
                if tr.quantity is not None:
                    q = Decimal(str(tr.quantity))
                    total_shares = max(Decimal("0"), total_shares - q)
                elif tr.ratio is not None:
                    r = Decimal(str(tr.ratio))
                    total_shares = total_shares * r

                if tr.cash_amount is not None:
                    c = Decimal(str(tr.cash_amount))
                    total_cost = max(Decimal("0"), total_cost - c)
            elif ttype == "cash_dividend":
                pass

        avg_cost = (total_cost / total_shares) if total_shares > 0 else Decimal("0")
        return total_shares, avg_cost

    @app.post("/api/instruments")
    def create_instrument() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        market = (body.get("market") or "").strip().lower()
        valid_markets = {"tw_stock", "us_stock", "fund", "other"}
        if market not in valid_markets:
            return json_response(400, f"市場別 (market) 必須為下列之一: {', '.join(sorted(valid_markets))}", None)

        symbol = (body.get("symbol") or "").strip().upper()
        if not symbol:
            return json_response(400, "標的代號 (symbol) 為必填項目", None)

        name = (body.get("name") or "").strip()
        if not name:
            return json_response(400, "標的名稱 (name) 為必填項目", None)

        currency = (body.get("currency") or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        existing = Instrument.query.filter_by(market=market, symbol=symbol).first()
        if existing:
            return json_response(400, "該市場下已存在相同的標的代號", None)

        inst = Instrument(
            market=market,
            symbol=symbol,
            name=name,
            currency=currency,
        )
        db.session.add(inst)
        db.session.commit()
        return json_response(201, "投資標的建立成功", serialize_instrument(inst))

    @app.get("/api/instruments")
    def list_instruments() -> tuple[Any, int]:
        instruments = Instrument.query.order_by(Instrument.id.asc()).all()
        return json_response(200, "成功取得投資標的清單", [serialize_instrument(i) for i in instruments])

    @app.get("/api/instruments/<int:instrument_id>")
    def get_instrument(instrument_id: int) -> tuple[Any, int]:
        inst = db.session.get(Instrument, instrument_id)
        if not inst:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得投資標的資料", serialize_instrument(inst))

    @app.get("/api/instruments/<int:instrument_id>/holding")
    def get_instrument_holding(instrument_id: int) -> tuple[Any, int]:
        inst = db.session.get(Instrument, instrument_id)
        if not inst:
            return json_response(404, "找不到這一筆", None)

        total_shares, avg_cost = compute_instrument_holding(inst.id)

        data = {
            "instrument_id": inst.id,
            "quantity": float(round(total_shares, 4)),
            "average_cost": float(round(avg_cost, 4)),
            "currency": inst.currency,
        }
        return json_response(200, "成功取得持有股數與平均成本", data)

    @app.post("/api/trades")
    def create_trade() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        inst_id_raw = body.get("instrument_id")
        if inst_id_raw is None:
            return json_response(400, "投資標的 (instrument_id) 為必填項目", None)
        try:
            instrument_id = int(inst_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "標的編號必須為整數", None)

        inst = db.session.get(Instrument, instrument_id)
        if not inst:
            return json_response(400, "指名的投資標的代號不存在", None)

        acc_id_raw = body.get("account_id")
        if acc_id_raw is None:
            return json_response(400, "帳戶 (account_id) 為必填項目", None)
        try:
            account_id = int(acc_id_raw)
        except (ValueError, TypeError):
            return json_response(400, "帳戶編號必須為整數", None)

        acc = db.session.get(Account, account_id)
        if not acc:
            return json_response(400, "指名的帳戶不存在", None)

        trade_type = (body.get("trade_type") or "").strip().lower()
        valid_trade_types = {
            "buy", "sell", "cash_dividend", "stock_dividend",
            "drip", "split", "merge", "capital_reduction",
        }
        if trade_type not in valid_trade_types:
            return json_response(400, f"交易種類 (trade_type) 必須為下列之一: {', '.join(sorted(valid_trade_types))}", None)

        traded_on_raw = body.get("traded_on")
        if not traded_on_raw:
            return json_response(400, "交易日期 (traded_on) 為必填項目", None)
        try:
            traded_on = date.fromisoformat(str(traded_on_raw))
        except ValueError:
            return json_response(400, "交易日期格式不正確 (YYYY-MM-DD)", None)

        currency = (body.get("currency") or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        fx_rate_raw = body.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            return json_response(400, "換算匯率 (fx_rate_to_twd) 為必填項目", None)
        try:
            fx_rate = Decimal(str(fx_rate_raw))
            if fx_rate <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "換算匯率必須大於 0", None)

        # Parse optional fields
        quantity = None
        qty_raw = body.get("quantity")
        if qty_raw is not None and str(qty_raw).strip() != "":
            try:
                quantity = Decimal(str(qty_raw))
            except Exception:
                return json_response(400, "股數 (quantity) 格式不正確", None)

        price = None
        price_raw = body.get("price")
        if price_raw is not None and str(price_raw).strip() != "":
            try:
                price = Decimal(str(price_raw))
            except Exception:
                return json_response(400, "價格 (price) 格式不正確", None)

        cash_amount = None
        cash_raw = body.get("cash_amount")
        if cash_raw is not None and str(cash_raw).strip() != "":
            try:
                cash_amount = Decimal(str(cash_raw))
            except Exception:
                return json_response(400, "現金金額 (cash_amount) 格式不正確", None)

        ratio = None
        ratio_raw = body.get("ratio")
        if ratio_raw is not None and str(ratio_raw).strip() != "":
            try:
                ratio = Decimal(str(ratio_raw))
            except Exception:
                return json_response(400, "比例 (ratio) 格式不正確", None)

        fee = None
        fee_raw = body.get("fee")
        if fee_raw is not None and str(fee_raw).strip() != "":
            try:
                fee = Decimal(str(fee_raw))
                if fee < 0:
                    raise ValueError()
            except Exception:
                return json_response(400, "手續費 (fee) 必須大於或等於 0", None)

        tax = None
        tax_raw = body.get("tax")
        if tax_raw is not None and str(tax_raw).strip() != "":
            try:
                tax = Decimal(str(tax_raw))
                if tax < 0:
                    raise ValueError()
            except Exception:
                return json_response(400, "交易稅 (tax) 必須大於或等於 0", None)

        # Validate required parameters per trade type
        if trade_type in ("buy", "sell", "drip"):
            if quantity is None or quantity <= 0:
                return json_response(400, f"{trade_type} 交易之股數 (quantity) 必須大於 0", None)
            if price is None or price <= 0:
                return json_response(400, f"{trade_type} 交易之價格 (price) 必須大於 0", None)
        elif trade_type == "stock_dividend":
            if quantity is None or quantity <= 0:
                return json_response(400, "配股交易之股數 (quantity) 必須大於 0", None)
        elif trade_type in ("split", "merge"):
            if ratio is None or ratio <= 0:
                return json_response(400, f"{trade_type} 交易之比例 (ratio) 必須大於 0", None)
        elif trade_type == "cash_dividend":
            if cash_amount is None or cash_amount <= 0:
                return json_response(400, "現金股利交易之金額 (cash_amount) 必須大於 0", None)
        elif trade_type == "capital_reduction":
            has_reduction_param = (
                (cash_amount is not None and cash_amount > 0)
                or (quantity is not None and quantity > 0)
                or (ratio is not None and ratio > 0)
            )
            if not has_reduction_param:
                return json_response(400, "減資交易需提供有效的 cash_amount、quantity 或 ratio", None)

        # Check holding before sell or capital_reduction
        current_holding, _ = compute_instrument_holding(inst.id)
        if trade_type == "sell":
            if current_holding - quantity < 0:
                return json_response(400, "賣出股數超過目前持有股數，不得超賣", None)
        elif trade_type == "capital_reduction":
            if quantity is not None and current_holding - quantity < 0:
                return json_response(400, "減資扣減股數超過目前持有股數", None)

        # Check post_income
        post_income = body.get("post_income")
        should_post_income = (
            bool(post_income)
            and trade_type in ("cash_dividend", "capital_reduction")
            and cash_amount is not None
            and cash_amount > 0
        )

        income_category_id = None
        if should_post_income:
            cat_id_raw = body.get("income_category_id")
            if cat_id_raw is None:
                return json_response(400, "入帳分類編號 (income_category_id) 為必填項目", None)
            try:
                income_category_id = int(cat_id_raw)
            except (ValueError, TypeError):
                return json_response(400, "入帳分類編號必須為整數", None)

            cat = db.session.get(IncomeCategory, income_category_id)
            if not cat:
                return json_response(400, "指名的入帳分類不存在", None)

        try:
            trade = Trade(
                instrument_id=inst.id,
                account_id=acc.id,
                trade_type=trade_type,
                traded_on=traded_on,
                quantity=quantity,
                price=price,
                cash_amount=cash_amount,
                ratio=ratio,
                fee=fee,
                tax=tax,
                currency=currency,
                fx_rate_to_twd=fx_rate,
            )
            db.session.add(trade)
            db.session.flush()

            if should_post_income:
                income = Income(
                    received_on=traded_on,
                    amount=cash_amount,
                    currency=currency,
                    fx_rate_to_twd=fx_rate,
                    category_id=income_category_id,
                    account_id=acc.id,
                    source=f"{inst.name} ({inst.symbol}) {trade_type}",
                    note="投資交易現金款項",
                    trade_id=trade.id,
                )
                db.session.add(income)

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return json_response(201, "交易建立成功", serialize_trade(trade))

    @app.get("/api/trades")
    def list_trades() -> tuple[Any, int]:
        query = Trade.query

        inst_id_param = request.args.get("instrument_id")
        if inst_id_param:
            try:
                query = query.filter(Trade.instrument_id == int(inst_id_param))
            except (ValueError, TypeError):
                return json_response(400, "標的編號必須為整數", None)

        acc_id_param = request.args.get("account_id")
        if acc_id_param:
            try:
                query = query.filter(Trade.account_id == int(acc_id_param))
            except (ValueError, TypeError):
                return json_response(400, "帳戶編號必須為整數", None)

        trades = query.order_by(Trade.traded_on.desc(), Trade.id.desc()).all()
        return json_response(200, "成功取得交易清單", [serialize_trade(t) for t in trades])

    @app.post("/api/trades/<int:trade_id>/void")
    def void_trade(trade_id: int) -> tuple[Any, int]:
        trade = db.session.get(Trade, trade_id)
        if not trade:
            return json_response(404, "找不到這一筆", None)

        has_income = Income.query.filter_by(trade_id=trade.id).first()
        if has_income:
            return json_response(400, "此筆交易已有入帳紀錄，無法作廢", None)

        trade.voided_at = datetime.now(timezone.utc)
        trade.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return json_response(200, "交易已成功作廢", serialize_trade(trade))

    @app.get("/api/summary")
    def get_summary() -> tuple[Any, int]:
        month_param = (request.args.get("month") or "").strip()
        if not month_param or not re.match(r"^[0-9]{4}-(0[1-9]|1[0-2])$", month_param):
            return json_response(400, "月份 (month) 為必填查詢參數，格式需為 YYYY-MM（例如 2026-11）", None)

        try:
            parts = month_param.split("-")
            year = int(parts[0])
            m = int(parts[1])
            start_date = date(year, m, 1)
            if m in (1, 3, 5, 7, 8, 10, 12):
                last_day = 31
            elif m in (4, 6, 9, 11):
                last_day = 30
            else:
                is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
                last_day = 29 if is_leap else 28
            end_date = date(year, m, last_day)
        except Exception:
            return json_response(400, "月份 (month) 格式不正確", None)

        incomes = Income.query.filter(
            Income.received_on >= start_date,
            Income.received_on <= end_date,
        ).all()
        total_income_twd = Decimal("0")
        for inc in incomes:
            total_income_twd += Decimal(str(inc.amount)) * Decimal(str(inc.fx_rate_to_twd))

        expenses = Expense.query.filter(
            Expense.spent_on >= start_date,
            Expense.spent_on <= end_date,
        ).all()
        total_expense_twd = Decimal("0")
        for exp in expenses:
            total_expense_twd += Decimal(str(exp.amount)) * Decimal(str(exp.fx_rate_to_twd))

        data = {
            "month": month_param,
            "income_twd": float(round(total_income_twd, 2)),
            "expense_twd": float(round(total_expense_twd, 2)),
        }
        return json_response(200, "成功取得月度現金流摘要", data)

    def serialize_transfer(tr: Transfer) -> dict[str, Any]:
        return {
            "id": tr.id,
            "transferred_on": tr.transferred_on.isoformat() if tr.transferred_on else None,
            "amount": float(tr.amount) if tr.amount is not None else 0.0,
            "currency": tr.currency,
            "fx_rate_to_twd": float(tr.fx_rate_to_twd) if tr.fx_rate_to_twd is not None else 1.0,
            "from_account_id": tr.from_account_id,
            "to_account_id": tr.to_account_id,
            "note": tr.note,
            "created_at": tr.created_at.isoformat() if tr.created_at else None,
            "updated_at": tr.updated_at.isoformat() if tr.updated_at else None,
        }

    @app.post("/api/transfers")
    def create_transfer() -> tuple[Any, int]:
        body = request.get_json(silent=True) or {}

        transferred_on_raw = body.get("transferred_on")
        if not transferred_on_raw:
            return json_response(400, "轉帳日期 (transferred_on) 為必填項目", None)
        try:
            transferred_on = date.fromisoformat(str(transferred_on_raw))
        except ValueError:
            return json_response(400, "轉帳日期格式不正確 (YYYY-MM-DD)", None)

        amount_raw = body.get("amount")
        if amount_raw is None:
            return json_response(400, "轉帳金額 (amount) 為必填項目", None)
        try:
            amount = Decimal(str(amount_raw))
            if amount <= 0:
                raise ValueError()
        except Exception:
            return json_response(400, "轉帳金額必須大於 0", None)

        currency = (body.get("currency") or "TWD").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            return json_response(400, "幣別 (currency) 必須為 3 碼英文字母", None)

        fx_rate_raw = body.get("fx_rate_to_twd")
        if fx_rate_raw is None:
            if currency == "TWD":
                fx_rate = Decimal("1.000000")
            else:
                return json_response(400, "外幣轉帳之換算匯率 (fx_rate_to_twd) 為必填項目", None)
        else:
            try:
                fx_rate = Decimal(str(fx_rate_raw))
                if fx_rate <= 0:
                    raise ValueError()
            except Exception:
                return json_response(400, "換算匯率必須大於 0", None)

        from_acc_raw = body.get("from_account_id")
        if from_acc_raw is None:
            return json_response(400, "轉出帳戶 (from_account_id) 為必填項目", None)
        try:
            from_account_id = int(from_acc_raw)
        except (ValueError, TypeError):
            return json_response(400, "轉出帳戶編號必須為整數", None)

        to_acc_raw = body.get("to_account_id")
        if to_acc_raw is None:
            return json_response(400, "轉入帳戶 (to_account_id) 為必填項目", None)
        try:
            to_account_id = int(to_acc_raw)
        except (ValueError, TypeError):
            return json_response(400, "轉入帳戶編號必須為整數", None)

        if from_account_id == to_account_id:
            return json_response(400, "轉出帳戶與轉入帳戶不可相同", None)

        from_acc = db.session.get(Account, from_account_id)
        if not from_acc:
            return json_response(400, "指名的轉出帳戶不存在", None)

        to_acc = db.session.get(Account, to_account_id)
        if not to_acc:
            return json_response(400, "指名的轉入帳戶不存在", None)

        raw_note = body.get("note")
        note = raw_note.strip() if isinstance(raw_note, str) and raw_note.strip() else None

        transfer = Transfer(
            transferred_on=transferred_on,
            amount=amount,
            currency=currency,
            fx_rate_to_twd=fx_rate,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            note=note,
        )
        db.session.add(transfer)
        db.session.commit()

        return json_response(201, "轉帳建立成功", serialize_transfer(transfer))

    @app.get("/api/transfers")
    def list_transfers() -> tuple[Any, int]:
        query = Transfer.query

        from_acc_param = request.args.get("from_account_id")
        if from_acc_param:
            try:
                query = query.filter(Transfer.from_account_id == int(from_acc_param))
            except (ValueError, TypeError):
                return json_response(400, "轉出帳戶編號必須為整數", None)

        to_acc_param = request.args.get("to_account_id")
        if to_acc_param:
            try:
                query = query.filter(Transfer.to_account_id == int(to_acc_param))
            except (ValueError, TypeError):
                return json_response(400, "轉入帳戶編號必須為整數", None)

        date_from_param = request.args.get("date_from")
        if date_from_param:
            try:
                parsed_from = date.fromisoformat(date_from_param)
                query = query.filter(Transfer.transferred_on >= parsed_from)
            except ValueError:
                return json_response(400, "起始日期格式不正確 (YYYY-MM-DD)", None)

        date_to_param = request.args.get("date_to")
        if date_to_param:
            try:
                parsed_to = date.fromisoformat(date_to_param)
                query = query.filter(Transfer.transferred_on <= parsed_to)
            except ValueError:
                return json_response(400, "結束日期格式不正確 (YYYY-MM-DD)", None)

        transfers = query.order_by(Transfer.transferred_on.desc(), Transfer.id.desc()).all()
        return json_response(200, "成功取得轉帳清單", [serialize_transfer(t) for t in transfers])

    @app.get("/api/transfers/<int:transfer_id>")
    def get_transfer(transfer_id: int) -> tuple[Any, int]:
        tr = db.session.get(Transfer, transfer_id)
        if not tr:
            return json_response(404, "找不到這一筆", None)
        return json_response(200, "成功取得轉帳資料", serialize_transfer(tr))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
