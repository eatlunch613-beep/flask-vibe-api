from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.json.ensure_ascii = False

tasks: list[dict[str, Any]] = [
    {"id": 1, "title": "整理專案需求", "description": "確認 API 的功能與規格"},
    {"id": 2, "title": "建立任務 API", "description": "實作任務清單與新增功能"},
]
next_task_id = max((task["id"] for task in tasks), default=0) + 1


def json_response(
    status: str, message: str, data: Any, http_status: int
) -> tuple[Any, int]:
    return jsonify(
        {"status": status, "message": message, "data": data}
    ), http_status


@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException) -> tuple[Any, int]:
    http_status = error.code or 500
    message = "找不到此路徑" if http_status == 404 else error.description
    return json_response("error", message, None, http_status)


@app.errorhandler(Exception)
def handle_unexpected_exception(error: Exception) -> tuple[Any, int]:
    app.logger.exception("Unhandled error while processing request")
    return json_response("error", "伺服器發生未預期錯誤", None, 500)


@app.get("/api/health")
def health() -> tuple[Any, int]:
    return json_response(
        "success",
        "服務正常",
        {
            "status": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        200,
    )


@app.get("/api/tasks")
def get_tasks() -> tuple[Any, int]:
    return json_response("success", "取得任務清單成功", tasks, 200)


@app.post("/api/tasks")
def create_task() -> tuple[Any, int]:
    global next_task_id

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return json_response("error", "請提供合法的 JSON 物件", None, 400)

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return json_response("error", "必填欄位 title 不可為空", None, 400)

    description = payload.get("description", "")
    if not isinstance(description, str):
        return json_response("error", "欄位 description 必須是字串", None, 400)

    task = {
        "id": next_task_id,
        "title": title.strip(),
        "description": description,
    }
    tasks.append(task)
    next_task_id += 1

    return json_response("success", "新增任務成功", task, 201)


@app.get("/api/tasks/<int:task_id>")
def get_task(task_id: int) -> tuple[Any, int]:
    task = next((item for item in tasks if item["id"] == task_id), None)
    if task is None:
        return json_response("error", "找不到指定任務", None, 404)
    return json_response("success", "取得任務成功", task, 200)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
