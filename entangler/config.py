import pathlib

from dynaconf import Dynaconf


settings = Dynaconf(
    settings_files=[pathlib.Path(__file__).parent / "settings.toml"],
)
