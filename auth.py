import os
from flask_login import LoginManager, UserMixin
from ldap3 import Server, Connection, ALL

login_manager = LoginManager()

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def authenticate_user(username, password):
    server = Server(os.getenv('LDAP_SERVER'), get_info=ALL)
    user_dn = os.getenv('LDAP_USER_DN').format(username=username)
    try:
        conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        if conn.bind():
            return True
    except Exception as e:
        print(f"LDAP authentication failed: {e}")
    return False
