from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis

from app.config import get_settings
from app.mqtt import PahoMqttPublisher
from app.routers import health, sightings
from app.store.valkey_store import ValkeySightingStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = Redis(host=settings.valkey_host, port=settings.valkey_port, decode_responses=True)
    app.state.store = ValkeySightingStore(client)
    app.state.mqtt_publisher = PahoMqttPublisher(
        settings.mqtt_host, settings.mqtt_port, settings.mqtt_topic, settings.public_api_base_url
    )
    yield
    client.close()
    app.state.mqtt_publisher.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Whale Sightings", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(sightings.router)

    return app


app = create_app()
