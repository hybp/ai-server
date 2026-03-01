from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    task_queue: str = "ai.task"

    google_api_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""

    be_base_url: str = "http://localhost:8080"
    be_bearer_token: str = ""

    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
