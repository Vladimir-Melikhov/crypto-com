from app.config import get_settings
from app.tasks.celery_app import create_celery_app

# Celery CLI ищет готовый экземпляр приложения:
# celery -A app.worker:celery_app worker
celery_app = create_celery_app(get_settings())
