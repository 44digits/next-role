from dataclasses import dataclass


@dataclass(frozen=True)
class JobPosting:
    title: str
    url: str
    description: str = ""
    location: str | None = None


@dataclass(frozen=True)
class PostingPage:
    postings: tuple[JobPosting, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ImportResult:
    job_id: int
    created: bool
    status: str


@dataclass
class RunSummary:
    companies: int = 0
    sites: int = 0
    pages: int = 0
    postings_seen: int = 0
    imported: int = 0
    duplicates: int = 0
    skipped_keywords: int = 0
    skipped_location: int = 0
    location_unknown: int = 0
    failures: int = 0

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def as_dict(self) -> dict[str, int]:
        return {
            "companies": self.companies,
            "sites": self.sites,
            "pages": self.pages,
            "postings_seen": self.postings_seen,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "skipped_keywords": self.skipped_keywords,
            "skipped_location": self.skipped_location,
            "location_unknown": self.location_unknown,
            "failures": self.failures,
        }
