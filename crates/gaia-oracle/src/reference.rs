use serde::{Deserialize, Serialize};

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum ReferenceSource {
    Gbif, INaturalist, IucnRedList, GlobalForestWatch, Ipbes,
}
impl ReferenceSource {
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Gbif => "GBIF (Global Biodiversity Information Facility)",
            Self::INaturalist => "iNaturalist",
            Self::IucnRedList => "IUCN Red List",
            Self::GlobalForestWatch => "Global Forest Watch",
            Self::Ipbes => "IPBES",
        }
    }
    pub fn base_url(&self) -> &'static str {
        match self {
            Self::Gbif => "https://api.gbif.org/v1",
            Self::INaturalist => "https://api.inaturalist.org/v1",
            Self::IucnRedList => "https://apiv3.iucnredlist.org/api/v3",
            Self::GlobalForestWatch => "https://data-api.globalforestwatch.org",
            Self::Ipbes => "https://ipbes.net",
        }
    }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize, Debug)]
pub enum ValidationOutcome {
    Valid,
    Invalid { reason: String },
    Unavailable { source: ReferenceSource },
}

pub trait ReferenceDataset: Send + Sync {
    fn source(&self) -> ReferenceSource;
    fn validate(&self, input_ref: &str, output_json: &str) -> ValidationOutcome;
}

/// Stub implementation for testing — always returns Valid.
pub struct StubReferenceDataset { source: ReferenceSource }
impl StubReferenceDataset {
    pub fn new(source: ReferenceSource) -> Self { Self { source } }
}
impl ReferenceDataset for StubReferenceDataset {
    fn source(&self) -> ReferenceSource { self.source.clone() }
    fn validate(&self, _: &str, _: &str) -> ValidationOutcome { ValidationOutcome::Valid }
}
