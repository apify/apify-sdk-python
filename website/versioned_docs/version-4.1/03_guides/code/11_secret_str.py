from pydantic import BaseModel, SecretStr


class ActorInput(BaseModel):
    # Masked in logs and `model_dump()`; read the plaintext with `get_secret_value()`.
    api_token: SecretStr


actor_input = ActorInput.model_validate({'api_token': 'my-secret-token'})
token = actor_input.api_token.get_secret_value()
