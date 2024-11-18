

class _KnownInputKey(str):
    __slots__ = ('_name',)
    def __init__(self, name: str) -> None:
        self._name = name

    def __str__(self) -> str:
        return self._name

    def __repr__(self) ->str:
        return str(self)

class _StartUrls(_KnownInputKey):
    url='url'
    requestsFromUrl = 'requestsFromUrl'  # noqa: N815  # Intentional to respect actual naming of input keys.
    method='method'
    payload= 'payload'
    userData='userData'  # noqa: N815  # Intentional to respect actual naming of input keys.
    headers='headers'


class _ActorInputKeys:
    # Helper class to have actor input strings all in one place and easy to use with code completion.
    startUrls: _StartUrls = _StartUrls('startUrls')  # noqa: N815  # Intentional to respect actual naming of input keys.
    # More inputs should be gradually added

ActorInputKeys = _ActorInputKeys()
