from typing import Generic, TypeVar
from app.repositories.base import BaseRepository

RepositoryType = TypeVar("RepositoryType", bound=BaseRepository)


class BaseService(Generic[RepositoryType]):
    """
    Generic base service that wraps a repository to perform business operations.
    """
    def __init__(self, repository: RepositoryType):
        self.repository = repository
