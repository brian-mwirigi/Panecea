# Pydantic model for Contract A: the extraction output schema pushed from the PDF parser to the Vultr Vector Store.

from pydantic import BaseModel


class AllowedPort(BaseModel):
    port: int
    protocol: str
    reason: str


class ContractA(BaseModel):
    device_model: str
    firmware_version: str
    allowed_ports: list[AllowedPort]
    source_doc_id: str
