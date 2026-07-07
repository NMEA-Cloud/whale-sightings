from fastapi import Request

from app.store.base import SightingStore


def get_store(request: Request) -> SightingStore:
    return request.app.state.store
