from datetime import datetime, timedelta

from app.modules.auth.models import User
from core.repositories.BaseRepository import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__(User)

    def create(self, commit: bool = True, **kwargs):
        password = kwargs.pop("password")
        instance = self.model(**kwargs)
        instance.set_password(password)
        self.session.add(instance)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return instance

    def get_by_email(self, email: str):
        return self.model.query.filter_by(email=email).first()

    def is_account_blocked(self, user: User) -> bool:
        """
        Verifica si el usuario está bloqueado por fuerza bruta.
        Regla: 5 o más intentos fallidos en los últimos 60 segundos.
        """
        if user.failed_login_attempts is None:
            return False

        if user.failed_login_attempts < 5:
            return False

        if user.failed_login_attempts >= 5:
            if user.last_failed_login:
                time_since_last_fail = datetime.utcnow() - user.last_failed_login

                if time_since_last_fail < timedelta(seconds=60):
                    return True
                else:
                    self.reset_failed_attempts(user)
                return False

        return False

    def reset_failed_attempts(self, user: User):
        """Resetea el contador a 0."""
        user.failed_login_attempts = 0
        user.last_failed_login = None
        self.session.commit()

    def register_failed_attempt(self, user: User):
        """
        Incrementa el contador de intentos fallidos y actualiza la hora.
        """
        user.failed_login_attempts += 1
        user.last_failed_login = datetime.utcnow()
        self.session.commit()
