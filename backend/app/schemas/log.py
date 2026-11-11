from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: str
    timestamp_ns: str
    line: str
    level: str | None = None
    container: str | None = None
    stream: str | None = None


class LogsResponse(BaseModel):
    query: str
    count: int
    logs: list[LogEntry]


class LogContainersResponse(BaseModel):
    count: int
    containers: list[str]
