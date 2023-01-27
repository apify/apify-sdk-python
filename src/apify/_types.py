from typing import Any, Dict, List, Union

# Type for representing json-serializable values
# It's close enough to the real thing supported by json.parse, and the best we can do until mypy supports recursive types
# It was suggested in a discussion with (and approved by) Guido van Rossum, so I'd consider it correct enough
JSONSerializable = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
