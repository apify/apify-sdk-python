from pydantic import BaseModel, EmailStr, HttpUrl


class ActorInput(BaseModel):
    target_url: HttpUrl
    # `EmailStr` needs the `pydantic[email]` extra installed.
    contact_email: EmailStr
