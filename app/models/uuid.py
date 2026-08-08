from sqlalchemy import Column, String
import uuid


# defie a new and unique id
def uuid_pk():
    return Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
