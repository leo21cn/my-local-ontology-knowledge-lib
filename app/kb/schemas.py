from pydantic import BaseModel, Field


class CorpusCreate(BaseModel):
    name: str
    subdir: str
    ontology_prefix: str
    embedding_model: str = "text-embedding-v4"
    vector_dim: int = 1024
    chunk_max_chars: int = 700
    chunk_overlap: int = 60
    graph_expand_enabled: bool = True
    graph_weight: float = 1.0


class CorpusUpdate(BaseModel):
    name: str | None = None
    chunk_max_chars: int | None = None
    chunk_overlap: int | None = None
    graph_expand_enabled: bool | None = None
    graph_weight: float | None = None
    archived: bool | None = None


class SyncTrigger(BaseModel):
    scope: str = "all"
    file_path: str | None = None


class CorpusOrder(BaseModel):
    ids: list[str]


class RebuildTrigger(BaseModel):
    mode: str


class ExtractTrigger(BaseModel):
    scope: str = "all"
    file_path: str | None = None
    force: bool = False


class EditPending(BaseModel):
    local_name: str | None = None
    label: str | None = None
    definition: str | None = None
    aliases: list[str] | None = None
    domain: str | None = None
    range: str | None = None


class SearchFilters(BaseModel):
    tags: list[str] = Field(default_factory=list)
    time_from: float | None = None
    time_to: float | None = None
    class_iri: str | None = None


class SearchRequest(BaseModel):
    corpus_id: str
    query: str
    top_k: int = 10
    filters: SearchFilters = Field(default_factory=SearchFilters)


class OntClassIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    parent_iris: list[str] = Field(default_factory=list)
    disjoint_with: list[str] = Field(default_factory=list)
    equivalent_to: str | None = None
    aliases: list[str] = Field(default_factory=list)
    min_cardinality: int | None = None
    max_cardinality: int | None = None


class OntObjPropIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    domain_iri: str
    range_iri: str
    characteristics: list[str] = Field(default_factory=list)
    min_cardinality: int | None = None
    max_cardinality: int | None = None


class OntDataPropIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    domain_iri: str
    xsd_range: str = "http://www.w3.org/2001/XMLSchema#string"


class EntityIn(BaseModel):
    label: str
    class_iri: str
    aliases: list[str] = Field(default_factory=list)
    anchor: dict


class EntitiesMerge(BaseModel):
    keep: str
    drop: str


class EntitiesSplit(BaseModel):
    eid: str
    new_label: str
    class_iri: str | None = None
    anchors: list[dict]


class RelationIn(BaseModel):
    from_eid: str
    to_eid: str
    type_iri: str
    evidence_anchors: list[dict] = Field(default_factory=list)


class PendingResolve(BaseModel):
    action: str
    new_class_iri: str | None = None
