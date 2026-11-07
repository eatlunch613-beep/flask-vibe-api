from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from extensions import db


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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
