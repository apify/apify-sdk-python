from pydantic import BaseModel, HttpUrl


class ActorInput(BaseModel):
    target_url: HttpUrl
