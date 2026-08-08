from pydantic import BaseModel


class EvalPipelineInput(BaseModel):
    """
    Input schema for the evaluation pipeline.
    """

    tenant_id: str
    file: str
    runs: int
