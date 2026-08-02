from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis

from app.auth import build_jwks_client
from app.config import get_settings
from app.mqtt import PahoMqttPublisher
from app.routers import health, sightings, well_known
from app.store.valkey_store import ValkeySightingStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)
    app.state.store = ValkeySightingStore(client)
    app.state.mqtt_publisher = PahoMqttPublisher(
        settings.mqtt_host, settings.mqtt_port, settings.mqtt_topic, settings.public_api_base_url
    )
    app.state.jwks_client = build_jwks_client(settings)
    yield
    client.close()
    app.state.mqtt_publisher.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Whale Sightings", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
        # Without this, fetch() in admin/app.js can't read WWW-Authenticate cross-origin
        # even though it's on the wire — needed to discover resource_metadata on a 401.
        expose_headers=["WWW-Authenticate"],
    )

    app.include_router(health.router)
    app.include_router(sightings.router)
    app.include_router(well_known.router)

    return app


app = create_app()
