"""
Глобальные настройки приложения.

Загружаются из .env через pydantic-settings.
Конфиги клиентов загружаются отдельно через load_client_configs().
"""

import json
from pathlib import Path

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from configs.client_config_schema import ClientConfig


class AppSettings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    bot_token: str
    admin_ids: list[int] = []
    telegram_api_id: int = 0
    telegram_api_hash: str = ""

    # Пути
    data_path: Path = Path("./data")

    # Groq
    groq_api_key: str = ""

    @property
    def db_path(self) -> Path:
        return self.data_path / "global.db"

    @property
    def clients_path(self) -> Path:
        return self.data_path / "clients"

    @property
    def logs_path(self) -> Path:
        return self.data_path / "logs"


def load_client_configs(clients_path: Path) -> dict[str, ClientConfig]:
    """Загрузить и валидировать конфиги всех клиентов.

    Args:
        clients_path: Путь к папке data/clients/.

    Returns:
        Словарь {client_id: ClientConfig}.
    """
    configs: dict[str, ClientConfig] = {}

    if not clients_path.exists():
        logger.warning(f"Папка клиентов не найдена: {clients_path}")
        return configs

    for config_file in clients_path.glob("*/config.json"):
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            client_config = ClientConfig.model_validate(data)
            configs[client_config.client_id] = client_config
            logger.info(f"Загружен конфиг клиента: {client_config.client_id}")
        except Exception:
            logger.exception(f"Ошибка загрузки конфига: {config_file}")

    logger.info(f"Загружено клиентов: {len(configs)}")
    return configs


# Глобальный объект настроек
settings = AppSettings()
