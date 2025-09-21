import logging
import os
import ssl
from flask_login import LoginManager, UserMixin
from ldap3 import Server, Connection, ALL, Tls

login_manager = LoginManager()

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def authenticate_user(username, password):

    server = Server(
        os.getenv("LDAP_SERVER"),
        use_ssl=True,
        get_info=ALL,
    )

    domain = os.getenv("USER_DOMAIN")

    try:
        # auto_bind ensures bind happens immediately
        conn = Connection(server, user='{}@{}'.format(username, domain), password=password, auto_bind=True)
        log.info(f"LDAP authentication successful for user {username}.")
        conn.unbind()  # cleanup
        return True
    except Exception as e:
        log.warning(f"LDAP authentication failed: {e}")
        return False

