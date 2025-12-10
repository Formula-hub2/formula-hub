import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

from flask import request
from flask_login import current_user, login_user

from app.modules.auth.models import User, UserSession
from app.modules.auth.repositories import UserRepository
from app.modules.profile.models import UserProfile
from app.modules.profile.repositories import UserProfileRepository
from core.configuration.configuration import uploads_folder_name
from core.services.BaseService import BaseService


class AuthenticationService(BaseService):
    def __init__(self):
        super().__init__(UserRepository())
        self.user_profile_repository = UserProfileRepository()

    def login(self, email, password, remember=True):
        user = self.repository.get_by_email(email)

        if user is None:
            return False

        if self.repository.is_account_blocked(user):
            return False

        if user.check_password(password):
            login_user(user, remember=remember)
            self.repository.reset_failed_attempts(user)
            return True

        self.repository.register_failed_attempt(user)
        return False

    def is_email_available(self, email: str) -> bool:
        return self.repository.get_by_email(email) is None

    def create_with_profile(self, **kwargs):
        try:
            email = kwargs.pop("email", None)
            password = kwargs.pop("password", None)
            name = kwargs.pop("name", None)
            surname = kwargs.pop("surname", None)

            if not email:
                raise ValueError("Email is required.")
            if not password:
                raise ValueError("Password is required.")
            if not name:
                raise ValueError("Name is required.")
            if not surname:
                raise ValueError("Surname is required.")

            user_data = {"email": email, "password": password}

            profile_data = {
                "name": name,
                "surname": surname,
            }

            user = self.create(commit=False, **user_data)
            profile_data["user_id"] = user.id
            self.user_profile_repository.create(**profile_data)
            self.repository.session.commit()
        except Exception as exc:
            self.repository.session.rollback()
            raise exc
        return user

    def update_profile(self, user_profile_id, form):
        if form.validate():
            updated_instance = self.update(user_profile_id, **form.data)
            return updated_instance, None

        return None, form.errors

    def get_authenticated_user(self) -> User | None:
        if current_user.is_authenticated:
            return current_user
        return None

    def get_authenticated_user_profile(self) -> UserProfile | None:
        if current_user.is_authenticated:
            return current_user.profile
        return None

    def temp_folder_by_user(self, user: User) -> str:
        return os.path.join(uploads_folder_name(), "temp", str(user.id))

    "Obtiene un usuario por su email utilizando el repositorio."

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)

    "Verifica si la contraseña proporcionada es correcta."

    def verify_password(self, user: User, password: str) -> bool:
        return user.check_password(password)

    def is_current_session_valid(self) -> bool:
        """Verifica si la sesión actual del usuario es válida."""
        if not current_user.is_authenticated:
            return False
        from flask import session as flask_session

        current_token = flask_session.get("session_token")
        current_session_id = flask_session.get("session_id")
        if not current_token or not current_session_id:
            return False
        session_obj = UserSession.query.filter_by(
            session_id=current_session_id, flask_session_token=current_token, user_id=current_user.id
        ).first()
        return session_obj is not None

    def create_user_session(self, user: User):
        """Crea una nueva sesión activa para el usuario."""
        session_id = str(uuid.uuid4())

        flask_session_token = hashlib.sha256(
            f"{session_id}{datetime.now(timezone.utc).timestamp()}".encode()
        ).hexdigest()
        user_session = UserSession(
            user_id=user.id,
            session_id=session_id,
            user_agent=request.headers.get("User-Agent"),
            ip_address=request.remote_addr,
            device_id=request.cookies.get("device_id"),
            flask_session_token=flask_session_token,
        )
        self.repository.session.add(user_session)
        self.repository.session.commit()

        from flask import session as flask_session

        flask_session["session_token"] = flask_session_token
        return user_session

    def get_active_sessions(self, user: User):
        """Devuelve todas las sesiones activas del usuario."""
        return UserSession.query.filter_by(user_id=user.id).all()

    def terminate_session(self, session_id: str):
        """Elimina una sesión activa específica."""
        session_obj = UserSession.query.filter_by(session_id=session_id).first()
        if session_obj:
            self.repository.session.delete(session_obj)
            self.repository.session.commit()
            return True
        return False

    def verify_session_token(self, token: str, user_id: int) -> bool:
        """Verifica si un token de sesión es válido para un usuario."""
        if not token:
            return False
        session_obj = UserSession.query.filter_by(flask_session_token=token, user_id=user_id).first()
        return session_obj is not None

    def get_session_by_token(self, token: str):
        """Obtiene una sesión por su token."""
        return UserSession.query.filter_by(flask_session_token=token).first()

    def terminate_all_other_sessions(self, user: User, current_session_id: str):
        """Elimina todas las sesiones del usuario excepto la actual."""
        UserSession.query.filter(UserSession.user_id == user.id, UserSession.session_id != current_session_id).delete()
        self.repository.session.commit()

    def get_remaining_seconds(self, user):
        if user.failed_login_attempts >= 5 and user.last_failed_login:
            time_since_fail = datetime.utcnow() - user.last_failed_login

            if time_since_fail < timedelta(seconds=60):
                return int(60 - time_since_fail.total_seconds())

        return 0
