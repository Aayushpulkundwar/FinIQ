# Import all the models, so that Base has them before being
# imported by Alembic.
from app.models.base import Base, BaseModel  # noqa

# Future database models must be imported here for Alembic migrations to detect them:
# from app.models.auth import User  # noqa
# from app.models.company import Company  # noqa
