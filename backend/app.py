import logging
from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge
from flask_cors import CORS
from backend.config import Config
from backend.db import init_db
from backend.routes.api import api_bp
from backend.routes.auth import auth_bp

logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 仅在开发环境 + SQLite 时自动创建表,生产环境依赖迁移工具
    if Config.DEBUG and Config.DATABASE_URL.startswith("sqlite"):
        try:
            logger.info(f"开发环境检测到,正在初始化数据库: {Config.DATABASE_URL}")
            init_db()
            logger.info("数据库表结构初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            # 开发环境直接抛出异常,方便尽早发现问题
            raise RuntimeError(f"数据库初始化失败,请检查配置: {e}") from e
    else:
        logger.info(f"生产环境或非 SQLite 数据库,跳过自动建表: {Config.DATABASE_URL}")

    # 配置 CORS(支持认证和自定义请求头)
    CORS(app, resources={
        r"/api/*": {
            "origins": Config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": Config.CORS_ALLOW_HEADERS,
            "supports_credentials": True,  # 支持 Cookie
        }
    })

    # 全局错误处理 - 请求体过大
    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_entity_too_large(error):
        logger.warning(f"请求体过大: {error}")
        return jsonify({
            "success": False,
            "error": f"上传内容过大,请求体不能超过 {Config.MAX_CONTENT_LENGTH // (1024 * 1024)}MB",
            "error_type": "payload_too_large"
        }), 413

    # 注册蓝图
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)

    @app.route('/')
    def index():
        return {
            "message": "RedInk AI图文生成器 API",
            "version": "0.2.0",
            "endpoints": {
                "health": "/api/health",
                "auth": {
                    "register": "POST /api/auth/register",
                    "login": "POST /api/auth/login",
                    "refresh": "POST /api/auth/refresh",
                    "logout": "POST /api/auth/logout",
                    "me": "GET /api/auth/me"
                },
                "outline": "POST /api/outline",
                "generate": "POST /api/generate",
                "images": "GET /api/images/<filename>",
                "history": "GET /api/history"
            }
        }

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG
    )
