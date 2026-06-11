"""Interactive Cookie task management web application."""

import json
from pathlib import Path

import pymysql
from flask import Flask, jsonify, render_template, request

from scheduler.config import validate_task_data
from services.jobs import submit_task_action
from storage.mysql import (
    create_task,
    delete_task,
    get_dashboard_stats,
    get_task,
    list_cookies,
    list_runs,
    list_tasks,
    set_task_enabled,
    update_task,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/tasks")
    def api_list_tasks():
        return jsonify(
            {
                "tasks": list_tasks(),
                "stats": get_dashboard_stats(),
            }
        )

    @app.get("/api/tasks/<int:task_id>")
    def api_get_task(task_id: int):
        task = get_task(task_id)
        if task is None:
            return jsonify({"error": "任务不存在"}), 404
        return jsonify({"task": task})

    @app.post("/api/tasks")
    def api_create_task():
        data, error = read_task_payload()
        if error:
            return jsonify({"error": error}), 400

        errors = validate_task_data(data)
        if errors:
            return jsonify({"error": "；".join(errors)}), 400

        try:
            task_id = create_task(data)
        except pymysql.err.IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                return jsonify({"error": "同一站点标识和账号已经登记"}), 409
            raise
        return jsonify({"id": task_id, "message": "任务已创建"}), 201

    @app.put("/api/tasks/<int:task_id>")
    def api_update_task(task_id: int):
        if get_task(task_id) is None:
            return jsonify({"error": "任务不存在"}), 404

        data, error = read_task_payload()
        if error:
            return jsonify({"error": error}), 400
        errors = validate_task_data(data)
        if errors:
            return jsonify({"error": "；".join(errors)}), 400

        try:
            update_task(task_id, data)
        except pymysql.err.IntegrityError as exc:
            if exc.args and exc.args[0] == 1062:
                return jsonify({"error": "同一站点标识和账号已经登记"}), 409
            raise
        return jsonify({"message": "任务已保存"})

    @app.delete("/api/tasks/<int:task_id>")
    def api_delete_task(task_id: int):
        if not delete_task(task_id):
            return jsonify({"error": "任务不存在"}), 404
        return jsonify({"message": "任务已删除"})

    @app.patch("/api/tasks/<int:task_id>/enabled")
    def api_toggle_task(task_id: int):
        data = request.get_json(silent=True) or {}
        if "enabled" not in data:
            return jsonify({"error": "缺少 enabled 字段"}), 400
        if not set_task_enabled(task_id, bool(data["enabled"])):
            return jsonify({"error": "任务不存在"}), 404
        return jsonify({"message": "任务状态已更新"})

    @app.post("/api/tasks/<int:task_id>/<action>")
    def api_run_action(task_id: int, action: str):
        if action not in {"probe", "refresh"}:
            return jsonify({"error": "不支持的操作"}), 404
        if get_task(task_id) is None:
            return jsonify({"error": "任务不存在"}), 404

        run_id, error = submit_task_action(task_id, action)
        if error:
            return jsonify({"error": error}), 409
        return jsonify({"run_id": run_id, "message": "任务已提交"}), 202

    @app.get("/api/runs")
    def api_list_runs():
        task_id = request.args.get("task_id", type=int)
        limit = min(request.args.get("limit", 50, type=int), 200)
        return jsonify({"runs": list_runs(task_id=task_id, limit=limit)})

    @app.get("/api/cookies")
    def api_list_cookies():
        return jsonify({"cookies": list_cookies()})

    @app.get("/api/scripts")
    def api_list_scripts():
        sites_dir = Path(app.root_path).parent / "refresher" / "sites"
        scripts = sorted(
            f"refresher.sites.{path.stem}"
            for path in sites_dir.glob("site_*.py")
            if path.stem != "__init__"
        )
        return jsonify({"scripts": scripts})

    @app.errorhandler(pymysql.MySQLError)
    def handle_mysql_error(exc):
        app.logger.exception("MySQL request failed")
        return jsonify({"error": f"数据库操作失败：{exc}"}), 500

    return app


def read_task_payload() -> tuple[dict | None, str]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, "请求数据格式错误"

    headers = data.get("headers", {})
    if isinstance(headers, str):
        if headers.strip():
            try:
                headers = json.loads(headers)
            except json.JSONDecodeError:
                return None, "请求头必须是合法 JSON"
        else:
            headers = {}
    if not isinstance(headers, dict):
        return None, "请求头必须是 JSON 对象"

    data["headers"] = headers
    data["enabled"] = bool(data.get("enabled", True))
    return data, ""
