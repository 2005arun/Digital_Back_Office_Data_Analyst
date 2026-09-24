import json
import secrets
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..db import Dataset, Message, Project, User, get_db
from ..services.analysis import answer_question
from ..services.llm import refine_answer
from ..services.profiling import profile_csv

router = APIRouter()
settings = get_settings()


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    dataset_ids: list[str] | None = None


@router.get("/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False, "user": None}
    user = db.get(User, user_id)
    if not user:
        request.session.clear()
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": {"id": user.id, "name": user.name, "email": user.email, "avatar_url": user.avatar_url}}


@router.get("/auth/login")
def auth_login(request: Request):
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured. Add credentials to .env.")
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/auth/callback")
async def auth_callback(request: Request, code: str = "", state: str = "", db: Session = Depends(get_db)):
    if not code or not secrets.compare_digest(state, request.session.pop("oauth_state", "")):
        raise HTTPException(status_code=400, detail="Invalid OAuth callback state")
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]
        profile_response = await client.get("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {access_token}"})
        profile_response.raise_for_status()
        profile = profile_response.json()
    user = db.scalar(select(User).where(User.google_sub == profile["sub"]))
    if not user:
        user = User(google_sub=profile["sub"], email=profile.get("email", ""), name=profile.get("name", "Analyst"), avatar_url=profile.get("picture"))
        db.add(user)
    else:
        user.email = profile.get("email", user.email)
        user.name = profile.get("name", user.name)
        user.avatar_url = profile.get("picture", user.avatar_url)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse(settings.frontend_url)


@router.post("/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/projects")
def list_projects(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    projects = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())).all()
    return [{"id": project.id, "name": project.name, "created_at": project.created_at.isoformat(), "datasets": len(project.datasets)} for project in projects]


@router.post("/projects")
def create_project(payload: ProjectCreate, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    project = Project(owner_id=user.id, name=payload.name.strip())
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "name": project.name, "created_at": project.created_at.isoformat(), "datasets": 0}


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": project.id, "name": project.name, "datasets": [{"id": item.id, "filename": item.filename, "profile": json.loads(item.profile_json)} for item in project.datasets]}


@router.post("/projects/{project_id}/datasets")
async def upload_dataset(project_id: str, request: Request, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    uploaded = []
    failed = []
    project_dir = settings.data_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        filename = file.filename or "Unnamed file"
        if not file.filename or not file.filename.lower().endswith(".csv"):
            failed.append({"filename": filename, "error": "File is not a CSV"})
            continue
        content = await file.read()
        if len(content) > settings.max_upload_bytes:
            failed.append({"filename": filename, "error": "File exceeds the upload size limit"})
            continue
        target = project_dir / f"{secrets.token_hex(12)}.csv"
        target.write_bytes(content)
        try:
            profile = profile_csv(target)
        except Exception as exc:
            target.unlink(missing_ok=True)
            failed.append({"filename": filename, "error": f"Could not parse CSV: {exc}"})
            continue
        dataset = Dataset(project_id=project.id, filename=filename, stored_path=str(target), profile_json=json.dumps(profile))
        db.add(dataset)
        uploaded.append({"filename": filename, "profile": profile})
    if not uploaded:
        detail = failed[0]["error"] if failed else "No files were uploaded"
        raise HTTPException(status_code=400, detail=detail)
    db.commit()
    return {"uploaded": uploaded, "failed": failed}


@router.post("/projects/{project_id}/datasets/{dataset_id}/ask")
def ask_dataset(project_id: str, dataset_id: str, payload: Question, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    dataset = db.scalar(select(Dataset).join(Project).where(Dataset.id == dataset_id, Dataset.project_id == project_id, Project.owner_id == user.id))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    source_datasets = [dataset]
    if payload.dataset_ids:
        source_datasets = db.scalars(select(Dataset).where(Dataset.project_id == project_id, Dataset.id.in_(payload.dataset_ids))).all()
        if {item.id for item in source_datasets} != set(payload.dataset_ids):
            raise HTTPException(status_code=400, detail="One or more selected datasets do not belong to this project")
    try:
        result = answer_question([Path(item.stored_path) for item in source_datasets], payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    llm_answer = None
    if not result.get("skip_refinement"):
        try:
            llm_answer = refine_answer(payload.question, result)
        except Exception:
            llm_answer = None
    if llm_answer:
        result["llm_answer"] = llm_answer
    db.add(Message(project_id=project_id, dataset_id=dataset_id, question=payload.question, answer=result.get("llm_answer", result["answer"]), method=result["method"]))
    db.commit()
    return result


@router.get("/projects/{project_id}/datasets/{dataset_id}/rows")
def dataset_rows(
    project_id: str,
    dataset_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    dataset = db.scalar(select(Dataset).join(Project).where(Dataset.id == dataset_id, Dataset.project_id == project_id, Project.owner_id == user.id))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    frame = pd.read_csv(dataset.stored_path)
    page = frame.iloc[offset:offset + limit]
    return {
        "rows": json.loads(page.to_json(orient="records", date_format="iso")),
        "columns": [str(column) for column in frame.columns],
        "total": len(frame),
        "offset": offset,
        "limit": limit,
    }


@router.get("/projects/{project_id}/messages")
def list_messages(project_id: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    messages = db.scalars(select(Message).where(Message.project_id == project_id).order_by(Message.created_at.asc())).all()
    return [{"id": message.id, "question": message.question, "answer": message.answer, "method": message.method, "created_at": message.created_at.isoformat()} for message in messages]
