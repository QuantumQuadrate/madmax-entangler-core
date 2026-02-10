import pathlib

from dynaconf import Dynaconf


# settings = Dynaconf(
#     settings_files=[pathlib.Path(__file__).parent / "settings.toml"],
# )


settings = Dynaconf(
    settings_files=["settings.toml", ".secrets.toml"],
    load_dotenv=True,
    environments=True,
)