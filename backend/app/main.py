from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DocumentTooLarge, OperationFailure

from app.config import get_settings
from app.db import get_db
from app.db.schema import initialize_database
from app.routers import auth, library, library_statistics, questions, responses, statistics, surveys


def create_app(initialize_schema: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if initialize_schema:
            initialize_database(get_db())
        yield

    app = FastAPI(title="问卷系统 API", version="0.1.0", lifespan=lifespan)

    def oversized_response() -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": "问卷、题目或答卷内容过大，超过单份文档的存储上限，请缩短内容后重试"})

    @app.exception_handler(DocumentTooLarge)
    async def document_too_large(request: Request, error: DocumentTooLarge) -> JSONResponse:
        return oversized_response()

    @app.exception_handler(OperationFailure)
    async def database_operation_failed(request: Request, error: OperationFailure) -> JSONResponse:
        if error.code == 10334:
            return oversized_response()
        raise error

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[get_settings().frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    app.include_router(auth.router)
    app.include_router(surveys.router)
    app.include_router(surveys.public_router)
    app.include_router(questions.router)
    app.include_router(library.banks_router)
    app.include_router(library.questions_router)
    app.include_router(library.shared_router)
    app.include_router(library_statistics.survey_router)
    app.include_router(library_statistics.library_router)
    app.include_router(responses.router)
    app.include_router(statistics.router)
    return app


app = create_app()
